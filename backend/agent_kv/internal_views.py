"""Internal APIs for the agent-kv cloud executor (spec §5.4).

Mounted under ``/internal/v1/agent-kv/`` and guarded ambiently by
``InternalAPIAuthMiddleware`` -- these views take empty auth/permission
classes. Most require ``org_id`` in the body of every request (they act on
one job belonging to one org); the two maintenance views, ``SweepView`` and
``TTLCleanupView``, are the exception -- they are platform-wide and take no
``org_id`` at all, since they sweep across every org in one call.
"""

import logging

from django.db.models import F, JSONField, Value
from django.db.models.expressions import CombinedExpression
from rest_framework.response import Response
from rest_framework.views import APIView

from agent_kv.dispatch import dispatch_terminal_webhook
from agent_kv.maintenance import run_sweep, run_ttl_cleanup
from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter
from agent_kv.storage import delete_input, delete_result_file, write_result

logger = logging.getLogger(__name__)

_VALID_STAGE_STATUSES = frozenset({"running", "done"})
# `name` is reserved too: `_status_document` builds each stage entry as
# `{"name": name, **stages_json[name]}`, and the spread comes LAST -- so a
# persisted `name` counter overrides it. That renames the stage in every later
# status response and breaks the `if name in stages_json` filter the document
# uses to decide which stages to show, i.e. one counter can make a job's
# progress disappear.
_RESERVED_STAGE_ENTRY_KEYS = frozenset({"status", "seconds", "name"})
_SCALAR_COUNTER_TYPES = (str, int, float, bool)


def _sanitize_counters(counters) -> dict:
    """Keep only scalar counters that can't clobber the reserved fields.

    Task-11-review ruling: ``counters`` is untrusted executor payload --
    a key of ``status``/``seconds`` must not be able to override the
    endpoint's own reserved fields, and a nested dict/list value must not
    be admitted into the persisted stage entry (only scalars are).
    """
    if not isinstance(counters, dict):
        return {}
    return {
        key: value
        for key, value in counters.items()
        if key not in _RESERVED_STAGE_ENTRY_KEYS
        and isinstance(value, _SCALAR_COUNTER_TYPES)
    }


def _attach_or_discard(job_id, org_id: str, result_ref: str, usage_summary) -> bool:
    """Keep a just-written result on a CANCELLED job, or delete it.

    Shared by the two ways a finalize can arrive for a job a cancel has already
    terminalized, which are NOT the same race and need to be told apart:

    * the cancel landed between this finalize's read and its ``mark_terminal``
      (``FinalizeView._complete`` lost the guard), and
    * the cancel landed earlier, so the row already read as CANCELLED and the
      finalize never attempted the guard at all
      (``FinalizeView._salvage``) -- which is the ORDINARY shape of this race,
      since the executor only learns of a cancel from its final stage report
      and then reports success with the full output anyway.

    Either way the engine has already flushed the run's OCR and LLM usage, so
    the customer has paid; the only question is whether the answer survives.

    Returns whether the result was kept. A refusal is the normal outcome for a
    duplicate callback (the row already carries a ``result_ref``) or a purged
    job, and the file written for THIS attempt is deleted so nothing is
    orphaned.
    """
    if AgentKVJob.attach_result_to_cancelled(
        job_id, org_id, result_ref=result_ref, usage_summary=usage_summary
    ):
        logger.info(
            "agent-kv job %s (org=%s) was cancelled after its extraction had "
            "finished; its usage was already flushed, so the paid-for result is "
            "KEPT and served alongside status=cancelled",
            job_id,
            org_id,
        )
        return True
    delete_result_file(result_ref)
    return False


def _stage_merge_expression(stage: str, entry: dict) -> CombinedExpression:
    """Build a DB-side jsonb merge expression for one stage's entry.

    Compiles (on Postgres) to ``"stages" || %s``, the jsonb ``||``
    concatenation operator, which does a shallow top-level merge: only the
    ``stage`` key in the JSON column is touched, every other key is left
    exactly as the current row has it. This is what makes the merge safe
    against two concurrent stage reports for two *different* stages racing
    each other -- a Python-side ``dict(job.stages or {})`` read, merge, and
    full-column ``.update(stages=...)`` would let whichever write lands
    second silently clobber the first (task-11-review ruling).
    """
    return CombinedExpression(
        F("stages"),
        "||",
        Value({stage: entry}, output_field=JSONField()),
        output_field=JSONField(),
    )


class StageReportView(APIView):
    """Merge one stage's progress into ``job.stages`` (spec §5.4).

    This endpoint is the sole write gate for ``job.stages``: only the
    defined shape (``status``, optional ``seconds``, plus sanitized flat
    ``counters``) is ever persisted -- unexpected top-level body keys, and
    any counter that collides with a reserved key or isn't a scalar, are
    dropped rather than stored, so a later status-endpoint spread of a
    stage entry can't leak arbitrary payload content (task-9 review).
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, job_id=None, **kwargs):
        body = request.data
        org_id = body.get("org_id")
        if not org_id:
            return Response({"detail": "org_id is required"}, status=400)
        stage = body.get("stage")
        if not stage:
            return Response({"detail": "stage is required"}, status=400)
        status_value = body.get("status")
        if status_value not in _VALID_STAGE_STATUSES:
            return Response({"detail": "status must be 'running' or 'done'"}, status=400)

        job_qs = AgentKVJob.objects.filter(id=job_id, organization_id=org_id).exclude(
            status__in=list(AgentKVJob.TERMINAL)
        )
        job = job_qs.first()
        if job is None:
            # Two very different situations used to share this response: a late
            # report for an already-terminal job (ordinary), and a report for a
            # job_id/org_id pair that matches NO row at all (never ordinary).
            #
            # The second is what an org-slug-vs-FK-pk mix-up looks like, and
            # `dispatch.py` documents that exact confusion shipping once
            # already. If it recurs, every stage report is a silent 200 no-op,
            # every job stays non-terminal and gets reaped as "Job timed out" --
            # a 100% failure rate presenting as timeouts, with nothing in any
            # log. So say which one happened.
            exists = AgentKVJob.objects.filter(id=job_id, organization_id=org_id).exists()
            if not exists:
                logger.warning(
                    "agent-kv stage report for unknown job %s (org=%s); no row "
                    "matches that job/org pair -- check the org identifier",
                    job_id,
                    org_id,
                )
            return Response(
                {
                    "ok": True,
                    "noop": True,
                    "reason": "already_terminal" if exists else "unknown_job",
                }
            )

        # `job.stage` is varchar(32). A longer name was an unhandled 500, and
        # `job.stages` could grow unbounded distinct keys from a misbehaving
        # or malicious executor.
        if not isinstance(stage, str):
            # A truthy non-string (e.g. `1`) passed the presence check above and
            # then raised TypeError at `len()` -- a 500 for a malformed report.
            return Response({"detail": "stage must be a string"}, status=400)
        if len(stage) > 32:
            return Response({"detail": "stage name too long"}, status=400)

        entry = {"status": status_value}
        if "seconds" in body:
            # Type-checked rather than taken verbatim: this is untrusted
            # executor payload and it is echoed back in the status document,
            # so a dict or list here was persisted and returned to the caller.
            seconds = body["seconds"]
            if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
                return Response({"detail": "seconds must be a number"}, status=400)
            entry["seconds"] = seconds
        entry.update(_sanitize_counters(body.get("counters")))

        updates = {
            "stages": _stage_merge_expression(stage, entry),
            "stage": stage,
        }
        if job.status in (JobStatus.PENDING, JobStatus.DISPATCHED):
            updates["status"] = JobStatus.RUNNING
        # Re-guarded at update time: job_qs still excludes TERMINAL, so if
        # the job raced to terminal between the read above and this
        # UPDATE's WHERE clause, this becomes a silent no-op too.
        job_qs.update(**updates)
        return Response({"ok": True})


class FinalizeView(APIView):
    """Terminalize a job: write its result (on success) then mark it done.

    Idempotent: a job already in a terminal state short-circuits before any
    write, with ONE exception -- a success callback for an already-``CANCELLED``
    job, which writes its result and attaches it (``_salvage``). A duplicate or
    late finalize still cannot rewrite an already-written result: the attach's
    guard requires a blank ``result_ref``, and a refused attach deletes the file
    that attempt wrote. The concurrency slot is always
    released, in a ``finally``, on every path that actually attempts to
    finalize (success, duplicate no-op, or an exception raised while
    finalizing) -- but never on a 400 for a malformed body, since nothing
    was finalized (and therefore nothing had a slot to release yet).

    On the success path, ``write_result`` unavoidably runs *before* the
    ``mark_terminal`` guard (the result has to exist to get a ``result_ref``
    to pass into it) -- so a guard-loss right after the write (a concurrent
    cancel/duplicate finalize won instead) leaves a result file on disk with
    no ref anywhere pointing at it. That orphan is cleaned up immediately via
    ``storage.delete_result_file`` rather than left to leak past even TTL
    cleanup (which only ever acts on a job's *stored* ``result_ref``).

    With ONE exception, and it is the reason this class changed: when the guard
    was lost to a CANCEL and the extraction had already finished, the result is
    attached to the cancelled row instead of deleted
    (``AgentKVJob.attach_result_to_cancelled``). The engine flushes its OCR and
    LLM usage before the executor's final stage report, so by then the customer
    has been billed -- deleting the file charged them for an answer and then
    destroyed it. The status stays ``cancelled``; only a pointer to paid-for
    work is added. Every other guard loss still deletes its own orphan, and the
    attach's own return value is what distinguishes them.

    Also deletes the staged input the moment ``mark_terminal`` actually
    wins (spec D10: "uploaded document deleted on job completion") -- the
    run is over either way, whether it completed or failed, so the input is
    no longer needed; the result file this same request may have just
    *successfully* written (guard won) is left completely untouched. Never
    runs on the duplicate/guard-lost path, since either another writer
    already owns cleanup or there's nothing new to terminalize.
    """

    authentication_classes: list = []
    permission_classes: list = []

    @staticmethod
    def _complete(job, job_id, org_id: str, body) -> tuple[bool, bool]:
        """Persist the result and terminalize as COMPLETED.

        Returns ``(finalized, result_attached)``: whether the terminal-state
        guard was won, and -- when it was NOT -- whether the result was
        nevertheless kept on a cancelled row.

        ``write_result`` unavoidably runs *before* the ``mark_terminal`` guard
        (the result has to exist to get a ``result_ref`` to pass in), so a
        guard-loss right after the write -- a concurrent cancel or duplicate
        finalize won instead -- leaves a result file with no ref anywhere
        pointing at it. That orphan is deleted here rather than left to leak
        past even TTL cleanup, which only ever acts on a job's *stored*
        ``result_ref``. Best-effort; never blocks the response.

        **A cancel that lost the race does not forfeit the result.** The window
        is real: the executor can finish extraction -- spending OCR and LLM,
        both already flushed by the engine before its final stage report -- and
        only then try that report, which is answered as a no-op because a cancel
        terminalized the row in the meantime. The executor returns success with
        the full output, this method writes it, and the guard below correctly
        declines to change a terminal row's status. Deleting the file at that
        point billed the customer for an answer and then destroyed it, with
        ``GET result`` reporting only ``{"success": false, "status":
        "cancelled"}``.

        So a CANCELLED row keeps it instead: ``attach_result_to_cancelled``
        attaches ``result_ref`` and ``usage_summary`` WITHOUT touching
        ``status`` or ``completed_at``, so the cancel stays honoured and
        ``mark_terminal`` remains the only way to reach a terminal state. The
        orphan delete still runs for every other guard loss -- a duplicate
        finalize against a COMPLETED row, say -- which is why the attach's
        return value decides, rather than the fact that the guard was lost.
        """
        result_ref = write_result(org_id, str(job_id), body.get("result") or {})
        finalized = AgentKVJob.mark_terminal(
            job_id,
            org_id,
            JobStatus.COMPLETED,
            result_ref=result_ref,
            usage_summary=body.get("usage_summary"),
        )
        if finalized:
            job.status = JobStatus.COMPLETED
            return True, False
        return False, _attach_or_discard(
            job_id, org_id, result_ref, body.get("usage_summary")
        )

    @staticmethod
    def _fail(job, job_id, org_id: str, body) -> tuple[bool, bool]:
        """Terminalize as FAILED. ``(guard won, False)``.

        The second element is always False: there is no result to attach to
        anything on a failure. It exists so both handlers share one shape and
        ``post`` can call whichever it picked without knowing which it got.
        """
        finalized = AgentKVJob.mark_terminal(
            job_id, org_id, JobStatus.FAILED, error=body.get("error") or ""
        )
        if finalized:
            job.status = JobStatus.FAILED
        return finalized, False

    @staticmethod
    def _salvage(job_id, org_id: str, body) -> bool:
        """Store a finished extraction's result on an ALREADY-cancelled job.

        **This is the ordinary shape of the cancelled-after-completion race, and
        the one `_complete` cannot reach.** `post` only calls a handler when the
        row it read was still non-terminal, so `_complete`'s own salvage covers
        a window of microseconds: the cancel landing between that read and
        `mark_terminal`. The real race is wider and earlier. The executor learns
        of a cancel from its final stage report, which the backend answers as a
        no-op once the row is terminal -- so by the time the callback worker
        calls finalize, the row has read CANCELLED for however long that round
        trip took, and `post` short-circuited before writing anything at all.
        The fully computed, already-billed output was simply dropped on the
        floor, and the one log line said "cancelled".

        So this writes it and attaches it. Deliberately narrow:

        * **success only.** A failed run has no result to keep.
        * **CANCELLED only.** A COMPLETED row already has its own result and a
          FAILED one legitimately has none; grafting a late callback's output
          onto either is the overwrite the terminal guard exists to prevent.
          `post` enforces the status, and
          `AgentKVJob.attach_result_to_cancelled` enforces it again in SQL.
        * **`status` and `completed_at` are never touched**, so the cancel stays
          won and `mark_terminal` remains the only route to a terminal state.
          This reports False as `finalized` for exactly that reason.
        * **The staged input is NOT dropped.** A cancelled job's input rides the
          TTL sweep (docs section 9), and `_drop_staged_input` stays gated on a
          won guard.

        Note that this writes a result for a job that was ALREADY terminal at
        read time, which the rest of this class is careful never to do. The
        idempotency that rule protected is preserved by the attach instead: its
        guard requires a blank `result_ref`, so a duplicate callback attaches
        nothing and `_attach_or_discard` deletes the file this attempt wrote.

        **The eligibility check runs BEFORE the write, not only after it.**
        `AgentKVJob.ATTACH_GUARD` is the one definition of what may be
        attached, and `can_attach_result` applies it as a read first. Without
        that, every redelivered callback for a job that already has its result
        -- and every callback that arrives after the caller DELETEd the job --
        wrote a fresh result file to object storage, had the guard refuse it,
        and then depended on `delete_result_file` to take it back out. That
        delete is best-effort by construction: it logs and returns, and the
        ref it would need to retry from was never persisted anywhere, so a
        single failed delete left a customer's extracted output sitting in the
        bucket with nothing pointing at it -- after a DELETE, or past the
        retention window. Those two cases are the ordinary ones under
        at-least-once delivery, and they no longer touch storage at all.

        The read is advisory, not a replacement for the guard: a cancel or a
        competing callback can still land between it and the UPDATE, and the
        UPDATE is what decides. What is left after this is the genuine race,
        and it is the same one `_complete` has always had -- see
        `storage.delete_job_files`, which reaps a job's directory so an orphan
        from either path is collected when the job is deleted or expires.
        """
        if not AgentKVJob.can_attach_result(job_id, org_id):
            logger.info(
                "agent-kv finalize for cancelled job %s (org=%s) has nothing to "
                "salvage -- the job already carries a result or its files have "
                "been purged; no result file was written",
                job_id,
                org_id,
            )
            return False
        result_ref = write_result(org_id, str(job_id), body.get("result") or {})
        return _attach_or_discard(job_id, org_id, result_ref, body.get("usage_summary"))

    @staticmethod
    def _drop_staged_input(job, job_id, org_id: str) -> None:
        """Delete the staged input now the run is over (spec D10).

        Only ever called when ``mark_terminal`` actually won, so it never runs
        on the duplicate/guard-lost path -- there, either another writer owns
        cleanup or there is nothing new to terminalize. A CANCELLED job never
        reaches here either: cancel goes through JobCancelView/mark_terminal
        directly, and a late finalize against an already-CANCELLED job loses
        the terminal guard, so a cancelled job's input rides the normal TTL
        sweep instead.

        The ref is blanked only when the file is confirmed gone -- otherwise it
        is the only handle TTL cleanup could retry from, and blanking it would
        orphan the uploaded document.
        """
        if delete_input(job):
            AgentKVJob.objects.filter(id=job_id, organization_id=org_id).update(
                input_ref=""
            )

    def post(self, request, *args, job_id=None, **kwargs):
        body = request.data
        org_id = body.get("org_id")
        if not org_id:
            return Response({"detail": "org_id is required"}, status=400)
        success = body.get("success")
        if not isinstance(success, bool):
            # Strict bool check (not truthy/falsy): a malformed/missing
            # `success` must 400 rather than silently fall through to the
            # failure branch and persist a FAILED job with an empty error.
            return Response({"detail": "success must be a boolean"}, status=400)

        job = AgentKVJob.objects.filter(id=job_id, organization_id=org_id).first()
        finalized = False
        result_attached = False
        try:
            if job is not None and job.status not in AgentKVJob.TERMINAL:
                handler = self._complete if success else self._fail
                finalized, result_attached = handler(job, job_id, org_id, body)
                if finalized:
                    # Queue the terminal webhook HERE, on the request that won
                    # the guard -- not in the callback worker after this
                    # response gets back to it. A lost response (timeout, 5xx)
                    # used to lose the notification outright: the worker
                    # retried, the replay reported `finalized: False`, and the
                    # worker declined to send because a non-fresh finalize is
                    # indistinguishable from the ordinary duplicate callback
                    # whose webhook already went out. Mirrors what the cancel
                    # path has always done, so exactly one of the two owns the
                    # notification for any job.
                    dispatch_terminal_webhook(job, job.status.lower())
                    self._drop_staged_input(job, job_id, org_id)
            elif job is not None and success and job.status == JobStatus.CANCELLED:
                # The job was already CANCELLED when this request read it, and
                # the executor still reported success with a full output --
                # which is what the cancelled-after-completion race actually
                # looks like, since a cancel is only noticed at the final stage
                # report. Keeping the result is the whole point of `_salvage`;
                # see it for why this is the only terminal status that gets a
                # second look, and why it still reports `finalized: False`.
                result_attached = self._salvage(job_id, org_id, body)
        finally:
            AgentKVConcurrencyLimiter.release(org_id, str(job_id))

        if job is None:
            logger.warning(
                "agent-kv finalize for unknown job %s (org=%s); no row matches "
                "that job/org pair, so nothing was terminalized -- the job (if "
                "it exists under another org identifier) will be reaped as a "
                "timeout",
                job_id,
                org_id,
            )

        return Response(
            {
                "finalized": finalized,
                "webhook_url": job.webhook_url if job else "",
                "status": job.status.lower() if job else "",
                # Lets the callback worker tell "already terminal" (ordinary)
                # from "no such job" (a wiring fault) -- they were byte-identical.
                "reason": "ok" if job else "unknown_job",
                # True only on the one path where `finalized` is False and the
                # caller still needs telling: the job was CANCELLED after its
                # extraction had finished, and the result was kept rather than
                # discarded. The cancellation webhook has already gone out by
                # then, so the callback worker sends a follow-up (see
                # `_maybe_webhook`). Additive: every other path reports False.
                "result_attached": result_attached,
            }
        )


class SweepView(APIView):
    """Terminalize PENDING-never-dispatched AND stuck jobs (spec §5.4).

    Thin wrapper: the two-phase sweep logic itself -- never-dispatched
    PENDING rows past ``AGENT_KV_SWEEP_GRACE_SECONDS`` and stuck
    DISPATCHED/RUNNING rows past ``AGENT_KV_STUCK_JOB_GRACE_SECONDS``, each
    idempotent and batch-capped -- lives in
    :func:`agent_kv.maintenance.run_sweep`, shared with the
    ``agent_kv_sweep`` management command (the Kubernetes CronJob mechanism
    for the cloud deployment). See that function's docstring for the full
    rationale.

    Platform-wide by design (no ``org_id`` in the body, unlike every other
    view in this module) -- it is invoked by a periodic maintenance
    mechanism (spec §5.4), not the cloud executor acting on one job/org.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        return Response(run_sweep())


class TTLCleanupView(APIView):
    """Delete staged files for expired jobs and blank their refs (spec §5.4).

    Thin wrapper: the cleanup logic itself -- deleting object-store paths
    for expired jobs and blanking their refs, idempotent and batch-capped --
    lives in :func:`agent_kv.maintenance.run_ttl_cleanup`, shared with the
    ``agent_kv_ttl_cleanup`` management command (the Kubernetes CronJob
    mechanism for the cloud deployment). See that function's docstring for
    the full rationale.

    Platform-wide by design, same as :class:`SweepView`.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        return Response(run_ttl_cleanup())
