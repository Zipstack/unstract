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
