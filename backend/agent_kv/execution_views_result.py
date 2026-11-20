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


def _terminal_payload(job) -> dict:
    """Return the result/outcome payload for a terminal ``job``.

    - COMPLETED: ``{success, status, extractors, usage_summary}`` -- the stored
      engine result namespaced per extractor (spec §7.3), not the bare blob.
    - FAILED: ``{"success": False, "status": "failed", "error": <user-safe>}``,
      plus ``extraction_salvaged: True`` and ``extractors`` when the run failed
      only at a later stage and handed over the extraction it had already
      completed and billed (today: a failed ``calculations`` run). ``success``
      stays False -- part of what the caller asked for did not happen.
    - CANCELLED: ``{"success": False, "status": "cancelled"}`` -- unless the
      cancel lost a race to an extraction that had already finished and been
      billed, in which case the paid-for result is served with ``success: True``
      alongside ``status: "cancelled"`` (see
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
            # carry it. This is the ONLY `success` describing the job.
            #
            # This used to add "each extractor keeps its own `success` inside
            # its own block", and the correction that replaced it over-reached
            # in the other direction: it said "No extractor does", which is
            # true of `table` and false of `kv`.
            #
            # `table` writes `tables`, `page_count`, `table_pages`, `headers`,
            # `row_count`, `detected` and `reason`, and its only nested
            # `success` belongs to `code_execution`, describing that step
            # rather than the extraction. That half stands, and it is the half
            # that cost real time -- an e2e scenario asserted a per-extractor
            # `success` and would have failed a successful Excel run.
            #
            # `kv` DOES carry one (`agentic_kv/src/engine/kv_extractor.py`
            # sets it), so a strict response model built from the stronger
            # claim would reject a valid `kv` result. It is only ever True in
            # a COMPLETED body: the engine sets it False on a failed
            # `calculations` run, and that fails the job, so the shape is the
            # FAILED one below.
            #
            # Either way this is the only `success` describing the JOB, which
            # is the part a client needs.
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
        failed: dict = {
            "success": False,
            "status": "failed",
            "error": job.error or "Job failed",
        }
        # A FAILED job can carry an extraction, and `success` stays False when
        # it does.
        #
        # The job really did fail -- a `calculations` run the caller asked for
        # did not produce output -- so saying otherwise would be a lie, and it
        # would be a BREAKING one: a client branching on `success` to decide
        # whether to run its error path would stop running it. The cancelled
        # race flips `success` to True for the opposite reason: nothing the
        # caller asked for failed there, the cancel was honoured and the answer
        # is whole. Here part of the request genuinely did not happen.
        #
        # So the extraction is additive instead, and `extraction_salvaged`
        # states it rather than leaving a client to probe for `extractors` on a
        # shape that has never carried it. Present only when it applies, the
        # same convention as the engine's advisory markers.
        #
        # No `usage_summary`: neither executor path that salvages has computed
        # one by the time it gives up. Its absence is not "free" -- the
        # extraction was billed; the figures are in `usage_v2`, which the
        # caller cannot read.
        if job.result_ref:
            failed["extraction_salvaged"] = True
            failed["extractors"] = {job.extractor: read_result(job.result_ref)}
        return failed
    # A cancel that lost the race to a finished extraction keeps its result
    # (`AgentKVJob.attach_result_to_cancelled`). The engine had already spent
    # and flushed the OCR and LLM usage by the time the cancel could collide
    # with the executor's final stage report, so the customer is billed either
    # way -- and destroying the answer on top of that was the strictly worse
    # half of the trade.
    #
    # `status` stays `cancelled`: the cancel WAS honoured and a client has to be
    # able to see that. `success` is True because there is a real result and it
    # was paid for. A client branching on `success` gets the data; one branching
    # on `status` sees the cancellation. Neither is misled.
    #
    # `result_ref` is blank for the ordinary cancel -- nothing ran, or the run
    # was stopped mid-flight -- which keeps that path byte-identical. A purged
    # job never reaches here: `JobResultView` 404s on `files_purged` before
    # calling this, which also covers the ref that survived a failed delete.
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


def result_payload(job) -> dict:
    """``_terminal_payload`` plus the caller's own inputs echoed back.

    A wrapper rather than four edits inside that function: it has four exit
    points (completed, failed, the cancel that lost its race, and the cancel
    that won), and an echo added to three of them would be worse than none --
    a client would have to know which terminal state it got before trusting
    the field.

    `custom_data` comes back as `{}` when none was sent, so a reader never
    tests for null as well as empty. It survives a purge, because it lives on
    the job row rather than in the stored blob `files_purged` destroys -- which
    is what keeps a purged job's response self-describing.
    """
    payload = _terminal_payload(job)
    payload["custom_data"] = job.custom_data or {}
    return payload
