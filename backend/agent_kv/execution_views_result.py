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

from agent_kv.models import JobStatus
from agent_kv.storage import read_result


def result_payload(job) -> dict:
    """Return the result/outcome payload for a terminal ``job``.

    - COMPLETED: ``{success, status, extractors, usage_summary}`` -- the stored
      engine result namespaced per extractor (spec §7.3), not the bare blob.
    - FAILED: ``{"success": False, "status": "failed", "error": <user-safe>}``.
    - CANCELLED: ``{"success": False, "status": "cancelled"}`` -- unless the
      cancel lost a race to a completed extraction, in which case the paid-for
      result is served with ``success: True`` and ``status: "cancelled"`` (see
      ``AgentKVJob.attach_result_to_cancelled``).

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
            # `success`/`status` stay at TOP level on every terminal payload --
            # completed, failed and cancelled alike -- so a client branches on
            # one key rather than having to know that only the failure shapes
            # carry it. They describe the JOB; each extractor keeps its own
            # `success` inside its own block.
            "success": True,
            "status": JobStatus.COMPLETED.lower(),
            "extractors": {job.extractor: read_result(job.result_ref)},
            # `total` stays the authoritative billing figure; `by_extractor`
            # exists so a multi-extractor job can be attributed. With one
            # extractor they are necessarily the same numbers.
            "usage_summary": {
                "total": usage,
                "by_extractor": {job.extractor: usage},
            },
        }
    if job.status == JobStatus.FAILED:
        return {
            "success": False,
            "status": "failed",
            "error": job.error or "Job failed",
        }
    # A cancel that lost the race to a completed extraction keeps its result
    # (`AgentKVJob.attach_result_to_cancelled`): the engine had already spent
    # and flushed the OCR/LLM usage, so the customer is billed either way, and
    # discarding the answer was the strictly worse half of that trade.
    #
    # `status` stays `cancelled` -- the cancel WAS honoured and a client must
    # still be able to see that -- but `success` is True and the result is
    # served, because there is a real result and it was paid for. A client that
    # branches only on `success` gets the data; one that branches on `status`
    # sees the cancellation. Neither is misled.
    #
    # `result_ref` is blank for the ordinary cancel (nothing ever ran, or the
    # run was stopped mid-flight), which keeps that path byte-identical.
    if job.result_ref:
        usage = job.usage_summary or {}
        return {
            "success": True,
            "status": "cancelled",
            "extractors": {job.extractor: read_result(job.result_ref)},
            "usage_summary": {
                "total": usage,
                "by_extractor": {job.extractor: usage},
            },
        }
    return {"success": False, "status": "cancelled"}
