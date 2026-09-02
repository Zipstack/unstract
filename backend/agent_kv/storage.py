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
    data = b"".join(chunk for chunk in uploaded_file.chunks())
    _fs().write(path=ref, mode="wb", data=data)
    return ref


def write_result(org_id: str, job_id: str, result: dict, *, nonce: str | None = None) -> str:
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


def delete_job_files(job) -> None:
    fh = _fs()
    for ref in (job.input_ref, job.result_ref):
        if not ref:
            continue
        try:
            fh.rm(path=ref)
        except Exception:
            logger.warning("agent-kv cleanup: could not remove %s", ref)


def delete_result_file(result_ref: str) -> None:
    """Best-effort delete of a result file that was just written but never
    got a ref persisted onto the job row.

    ``FinalizeView`` writes the result *before* attempting the terminal-
    state guard (spec §5.4); if the guard loses the race -- a concurrent
    cancel or a duplicate finalize won instead -- the file this call just
    wrote is orphaned: nothing anywhere points at it, so it would otherwise
    sit in object storage forever, past even TTL cleanup (which only acts on
    a job's *stored* ``result_ref``). Tolerant of the file being missing
    already, mirroring ``delete_input``/``delete_job_files``.
    """
    if not result_ref:
        return
    try:
        _fs().rm(path=result_ref)
    except Exception:
        logger.warning("agent-kv cleanup: could not remove orphaned %s", result_ref)


def delete_input(job) -> None:
    """Delete only the staged input file (spec D10: "uploaded document
    deleted on job completion"), tolerant of it being missing already.

    Deliberately narrower than ``delete_job_files``: it never touches
    ``result_ref``/the result file. ``FinalizeView`` calls this right after
    a job is fully terminalized, in the same request that may have just
    written the result -- that file must be left completely alone.
    """
    if not job.input_ref:
        return
    try:
        _fs().rm(path=job.input_ref)
    except Exception:
        logger.warning("agent-kv cleanup: could not remove %s", job.input_ref)
