"""Object-store staging/results for agent-kv (spec §5.4, §6.4).

Paths are the contract: {AGENT_KV_STORAGE_DIR_PREFIX}/{org_id}/{job_id}/input{ext}
and .../result.json. No document bytes ever ride the broker.

The prefix is bucket-rooted (default ``unstract/agent_kv``) like
``WORKFLOW_EXECUTION_DIR_PREFIX``/``API_EXECUTION_DIR_PREFIX``: s3fs/gcsfs read
the first path segment as the *bucket*, so a bucket-less root (the old
``org/{org_id}/...``) makes every write fail with ``NoSuchBucket``. The cloud
executor keys its OCR cache under the same root
(``{prefix}/{org_id}/cache/...``), so both sides must be configured alike.
"""

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from django.conf import settings

from unstract.filesystem import FileStorageType, FileSystem

logger = logging.getLogger(__name__)


def _fs():
    return FileSystem(FileStorageType.AGENT_KV).get_file_storage()


def _base(org_id: str, job_id: str) -> str:
    return f"{settings.AGENT_KV_STORAGE_DIR_PREFIX}/{org_id}/{job_id}"


def stage_input(org_id: str, job_id: str, uploaded_file) -> str:
    ext = os.path.splitext(uploaded_file.name or "")[1].lower() or ".bin"
    ref = f"{_base(org_id, job_id)}/input{ext}"
    data = b"".join(uploaded_file.chunks())
    _fs().write(path=ref, mode="wb", data=data)
    return ref


def write_result(
    org_id: str, job_id: str, result: dict, *, nonce: str | None = None
) -> str:
    """Write a job result and return its object-store ref.

    The path is UNIQUE per call (``.../result-<nonce>.json``, nonce defaulting
    to a fresh uuid4 hex) rather than a deterministic ``.../result.json``.
    ``FinalizeView`` writes the result BEFORE it attempts the terminal-state
    guard; on a concurrent duplicate-SUCCESS finalize, the guard loser must
    clean up ONLY the orphan it just wrote -- with a shared deterministic path
    it would instead delete the exact file the winning row's ``result_ref``
    points at, 500-ing the completed job's result endpoint / losing data
    (pre-Greptile critical #3). A unique ref per attempt makes the loser's
    ``delete_result_file`` target its own file and nothing else.

    Backward-tolerant: ``read_result``/``delete_job_files``/TTL cleanup all use
    the ref STORED on the job row, so any previously written ``result.json``
    ref remains readable and removable unchanged.
    """
    ref = f"{_base(org_id, job_id)}/result-{nonce or uuid.uuid4().hex}.json"
    _fs().json_dump(path=ref, data=result)
    return ref


def read_result(result_ref: str) -> dict:
    return _fs().json_load(path=result_ref)


def delete_job_files(job) -> list[str]:
    """Delete the job's staged input and result, returning the ref FIELD names
    that are now confirmed to point at nothing.

    The return value exists so a caller can blank only the refs whose files are
    actually gone. Blanking unconditionally -- what both callers used to do --
    loses the only handle to a file whose delete FAILED: TTL cleanup selects
    candidates by `input_ref > "" OR result_ref > ""`, so a blanked row drops
    out of the candidate set permanently and the object sits in the bucket
    forever, unreferenced and unbillable-to-anyone (Greptile review #3).

    A ref is reported clear when it was already empty (nothing was ever staged)
    or when the delete succeeded. ``FileNotFoundError`` counts as success: the
    goal is "the file is not there", and a ref whose object is already gone has
    nothing left to retry. Any other exception leaves the ref OUT of the
    returned list, so the caller keeps it and the next pass retries.
    """
    fh = _fs()
    cleared: list[str] = []
    for field in ("input_ref", "result_ref"):
        ref = getattr(job, field, "") or ""
        if not ref:
            cleared.append(field)
            continue
        try:
            fh.rm(path=ref)
        except FileNotFoundError:
            cleared.append(field)
        except Exception:
            # Left out of `cleared` deliberately -- the ref is the retry handle.
            logger.warning(
                "agent-kv cleanup: could not remove %s (ref kept for retry)",
                ref,
                exc_info=True,
            )
        else:
            cleared.append(field)
    if len(cleared) == 2:
        # Both named files are confirmed gone, so anything STILL under this
        # job's directory is an orphan -- a result file written by a finalize
        # that lost the attach guard and whose best-effort delete failed. It
        # has no ref anywhere, so this is the only pass that can ever see it.
        _reap_job_dir(job)
    return cleared


def _reap_job_dir(job) -> None:
    """Remove whatever is left under ``{prefix}/{org_id}/{job_id}/``.

    Both of a job's named files live in a directory of its own, so once
    ``input_ref`` and ``result_ref`` are confirmed deleted the directory is
    expected to be empty -- and on flat object storage a prefix with no
    objects left does not exist at all, which is why the common case costs one
    ``exists`` and stops. Anything the check does find is by definition
    unreferenced: a result file some finalize wrote before the attach guard
    refused it, whose ``delete_result_file`` then failed. Nothing records that
    ref, so neither TTL cleanup nor DELETE could otherwise reach it and the
    object would stay in the bucket permanently.

    Best-effort and last: it runs only after the named deletes have already
    succeeded, so a failure here cannot change which refs the caller blanks,
    and a job whose own file delete failed keeps its ref for retry exactly as
    before.

    ``rm_exact``, not ``rm``: ``rm`` hands its path to fsspec, which expands
    it as a glob on gcsfs/s3fs. The segments here are a UUID and an org id,
    which contain no glob metacharacters today -- but this is the house idiom
    for "delete this exact tree" and it costs nothing to not depend on that.

    **What this does not reach.** Candidacy still comes from the ref columns:
    ``run_ttl_cleanup`` selects rows with a non-blank ``input_ref`` or
    ``result_ref``, so a row that has already been fully cleaned (or DELETEd)
    is never visited again, and an orphan created AFTER that point is not
    collected here. ``FinalizeView._salvage``'s pre-flight is what keeps that
    case from arising in the ordinary redelivery-after-DELETE path; closing it
    for the genuine race needs a durable marker that outlives the refs, which
    is a separate piece of design.
    """
    job_dir = _base(str(job.organization_id), str(job.id))
    try:
        if not _fs().exists(job_dir):
            return
        _fs().rm_exact(job_dir)
    except Exception:
        logger.warning(
            "agent-kv cleanup: could not reap leftovers under %s",
            job_dir,
            exc_info=True,
        )
    else:
        logger.info("agent-kv cleanup: reaped unreferenced leftovers under %s", job_dir)


def delete_result_file(result_ref: str) -> None:
    """Best-effort delete of a result file that was just written but never
    got a ref persisted onto the job row.

    ``FinalizeView`` writes the result *before* attempting the terminal-
    state guard (spec §5.4); if the guard loses the race -- a concurrent
    cancel or a duplicate finalize won instead -- the file this call just
    wrote is orphaned: nothing anywhere points at it, so TTL cleanup cannot
    see it either -- that pass acts on a job's *stored* ``result_ref``.
    Tolerant of the file being missing already, mirroring
    ``delete_input``/``delete_job_files``.

    When this call FAILS the object stays, and there is no ref to retry from.
    ``delete_job_files`` reaps the job's whole directory once both named files
    are gone, which collects such an orphan the next time the job is deleted
    or expires -- provided the row is still a TTL candidate, i.e. still
    carries a ref. ``FinalizeView._salvage`` refuses up front rather than
    writing a file it knows will be refused, so the paths that reach this
    cleanup at all are now races rather than ordinary redeliveries.
    """
    if not result_ref:
        return
    try:
        _fs().rm(path=result_ref)
    except Exception:
        logger.warning("agent-kv cleanup: could not remove orphaned %s", result_ref)


def delete_input(job) -> bool:
    """Delete only the staged input file (spec D10: "uploaded document
    deleted on job completion"), returning whether ``input_ref`` is now
    confirmed to point at nothing.

    Deliberately narrower than ``delete_job_files``: it never touches
    ``result_ref``/the result file. ``FinalizeView`` calls this right after
    a job is fully terminalized, in the same request that may have just
    written the result -- that file must be left completely alone.

    Same confirmed-clear contract as ``delete_job_files``, and for the same
    reason: this swallowed every exception while its caller blanked
    ``input_ref`` unconditionally, so a transient object-store error orphaned
    the customer's uploaded document permanently -- TTL cleanup only selects
    rows that still carry a non-blank ref, so a blanked row can never be
    reconsidered. ``delete_job_files`` and its two callers were fixed for this
    in the Greptile round; THIS third site was missed, because the fix was
    applied by following the one function's callers rather than by grepping for
    every site that blanks a ref.

    True when there was nothing to delete or the file is gone (including
    already-missing); False when it is still there and the ref must be kept.
    """
    if not job.input_ref:
        return True
    try:
        _fs().rm(path=job.input_ref)
    except FileNotFoundError:
        return True
    except Exception:
        logger.warning(
            "agent-kv cleanup: could not remove %s (ref kept for retry)",
            job.input_ref,
            exc_info=True,
        )
        return False
    return True


#: The OCR document-cache tier, relative to an org's root.
_CACHE_DIR = "cache"


def _scan_offset(total: int) -> int:
    """Where this tick starts in the listing, so no prefix can starve the tail.

    Moves with the clock rather than at random: a run is reproducible within
    its hour, successive runs still cover the whole listing, and tests can
    pin it. Its own function so they can.
    """
    return int(datetime.now(UTC).timestamp() // 3600) % total


def sweep_document_cache(max_age_days: int, limit: int) -> tuple[int, int]:
    """Delete OCR document-cache entries older than ``max_age_days``.

    Returns ``(deleted, failed)``.

    **Why this is a separate sweep and not part of job cleanup.** Cache entries
    are CONTENT-addressed -- ``{prefix}/{org_id}/cache/{doc_sha256}-...json`` --
    so one entry may be the OCR of a document that several jobs, across time,
    all submitted. Deleting on job deletion would therefore throw away a live
    entry another job legitimately reads, and there is no job row to drive a
    row-wise sweep from. Age is the only correct axis.

    **Why not an object-store lifecycle rule instead.** ``org_id`` sits ABOVE
    ``cache/`` in the path and S3/MinIO lifecycle filters match a LITERAL
    prefix with no wildcard, so no single rule can select the cache tier across
    orgs. ``minio_ilm_setup.yaml`` covers ``execution/`` and ``api/`` precisely
    because those are literal roots; this tier is not reachable that way
    without restructuring the key, which would orphan every existing entry.

    **Deleting an entry is always safe**, which is what makes an unsynchronised
    sweep acceptable here: a miss costs one re-OCR and nothing else. That is
    not true of the job tree, which is why this does not share that code path.

    Capped at ``limit`` objects EXAMINED per call -- not deleted, see the note
    at the loop -- and tolerant of every per-object failure, in the style of the
    two sweeps in ``agent_kv.maintenance``: a cache that cannot be swept must
    never fail the maintenance tick.

    **The listing itself is still whole**, and that is a known limit rather than
    an oversight. ``FileStorage`` exposes ``glob``/``ls``/``walk`` and no cursor,
    so there is no paged scan to ask for: one call returns every matching key
    and the per-tick cost of THAT grows with the cache even though the stat and
    delete work no longer does. Closing it properly means either a cursor on the
    storage interface or a key layout that a lifecycle rule can select
    (``cache/{org}/...`` rather than ``{org}/cache/...``), both of which are
    larger changes than this sweep.
    """
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    pattern = f"{settings.AGENT_KV_STORAGE_DIR_PREFIX}/*/{_CACHE_DIR}/*.json"
    # `_fs()` is inside the guard, not above it: resolving the storage backend
    # RAISES where Agent-KV storage is not configured
    # (`FileStorageError: AGENT_KV_FILE_STORAGE_CREDENTIALS is unset`), and
    # this runs on every maintenance tick including one with nothing to do.
    # Before this sweep existed a no-candidate tick touched storage not at all,
    # so hoisting the call would turn a quiet no-op into a 500 on the TTL
    # endpoint for every deployment that never configured the bucket.
    try:
        fs = _fs()
        paths = fs.glob(pattern)
    except Exception as exc:
        logger.warning(
            "agent-kv cache sweep: listing %s failed (%s): %s",
            pattern,
            type(exc).__name__,
            exc,
        )
        return (0, 0)

    # EXAMINED, not acted-on, is what the budget counts, and the scan does not
    # always start at the front. Both were wrong in the first version and both
    # were reported by greptile on #2309:
    #
    # * counting only deletes and failures meant a store full of UNEXPIRED
    #   entries stat'ed every one of them on every tick while never reaching
    #   `limit`, so the per-tick cost grew with the cache and could hold the
    #   internal TTL endpoint past its caller's patience;
    # * starting at the front every time meant a prefix of entries that
    #   persistently fail -- an unreadable mtime, a delete the backend refuses
    #   -- consumed the whole budget on every run, and nothing behind them was
    #   ever reached. `run_ttl_cleanup` has the same hazard and solves it by
    #   splitting the batch between fresh rows and retries; there is no row
    #   here to mark, so rotation is the equivalent that needs no state.
    #
    # The offset moves with the clock rather than at random, so a run is
    # reproducible within its hour while successive runs still cover the whole
    # listing. Deleting a cache entry is always safe, so sweeping the tiers in
    # a different order on each tick costs nothing.
    total = len(paths)
    if not total:
        return (0, 0)
    offset = _scan_offset(total)

    deleted = failed = examined = 0
    for i in range(total):
        if examined >= limit:
            break
        path = paths[(offset + i) % total]
        examined += 1
        try:
            mtime = fs.modification_time(path)
        except FileNotFoundError:
            continue
        except Exception as exc:
            failed += 1
            logger.warning(
                "agent-kv cache sweep: mtime for %s failed (%s)",
                path,
                type(exc).__name__,
            )
            continue
        # A naive mtime is treated as UTC: the comparison must not raise, and
        # every backend that returns one stores UTC.
        if mtime.tzinfo is None:
            mtime = mtime.replace(tzinfo=UTC)
        if mtime >= cutoff:
            continue
        try:
            fs.rm(path=path)
            deleted += 1
        except FileNotFoundError:
            # Raced with another sweeper, or already gone: the end state is the
            # one this asked for, so it counts as deleted rather than failed.
            deleted += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                "agent-kv cache sweep: could not remove %s (%s)",
                path,
                type(exc).__name__,
            )
    if deleted or failed:
        logger.info(
            "agent-kv cache sweep: deleted=%s failed=%s older_than_days=%s",
            deleted,
            failed,
            max_age_days,
        )
    return (deleted, failed)
