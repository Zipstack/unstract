"""Result/outcome payload for a TERMINAL agent-kv job (spec §7.3).

Single source of truth for "what does the result endpoint hand back for a
job that's done", shared by ``JobResultView`` (``execution_views.py``) and
``SubmitView``'s synchronous-wait branch (Task 8, lazily imported to avoid a
circular import at module load time) -- both call this only once they've
already established the job is terminal, so it is total over
``AgentKVJob.TERMINAL`` and never raises for a terminal job (spec §7.3:
"Failed jobs: {success: false, error, timing} with a user-safe error").

Everything that depends on the caller's own status code (409 for a
non-terminal job at ``JobResultView``, vs. a plain 200 for any terminal
status at ``SubmitView``'s wait loop) -- and the expired/blank-``result_ref``
404 check -- lives in the caller instead; this function's only job is
building the right body once "terminal" is already a given.
"""

from agent_kv.constants import V1_EXTRACTOR_NAME
from agent_kv.models import JobStatus
from agent_kv.storage import read_result


def result_payload(job) -> dict:
    """Return the result/outcome payload for a terminal ``job``.

    - COMPLETED: the stored engine result, unchanged.
    - FAILED: ``{"success": False, "status": "failed", "error": <user-safe>}``.
    - CANCELLED: ``{"success": False, "status": "cancelled"}``.

    Callers are responsible for confirming ``job.status`` is terminal (and,
    for COMPLETED, that ``result_ref`` is non-blank and unexpired) before
    calling this -- it never raises for a job in any of the three states
    above.
    """
    if job.status == JobStatus.COMPLETED:
        # Wrapped at READ time, not stored wrapped: the stored blob is the
        # engine's own result object, and namespacing it here keeps the cloud
        # engine and every already-written result untouched (spec §7.3).
        usage = job.usage_summary or {}
        return {
            "extractors": {V1_EXTRACTOR_NAME: read_result(job.result_ref)},
            # `total` stays the authoritative billing figure; `by_extractor`
            # exists so a multi-extractor job can be attributed. With one
            # extractor they are necessarily the same numbers.
            "usage_summary": {
                "total": usage,
                "by_extractor": {V1_EXTRACTOR_NAME: usage},
            },
        }
    if job.status == JobStatus.FAILED:
        return {
            "success": False,
            "status": "failed",
            "error": job.error or "Job failed",
        }
    return {"success": False, "status": "cancelled"}
