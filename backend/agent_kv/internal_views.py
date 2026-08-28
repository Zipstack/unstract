"""Internal APIs for the agent-kv cloud executor (spec §5.4).

Mounted under ``/internal/v1/agent-kv/`` and guarded ambiently by
``InternalAPIAuthMiddleware`` -- these views take empty auth/permission
classes and instead require ``org_id`` in the body of every request.
"""

import logging

from rest_framework.response import Response
from rest_framework.views import APIView

from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter
from agent_kv.storage import write_result

logger = logging.getLogger(__name__)


class StageReportView(APIView):
    """Merge one stage's progress into ``job.stages`` (spec §5.4).

    This endpoint is the sole write gate for ``job.stages``: only the
    defined shape (``status``, optional ``seconds``, plus the flat
    ``counters`` dict) is ever persisted -- unexpected top-level body keys
    are ignored rather than stored, so a later status-endpoint spread of a
    stage entry can't leak arbitrary payload content (task-9 review).
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, job_id=None, **kwargs):
        body = request.data
        org_id = body.get("org_id")
        if not org_id:
            return Response({"detail": "org_id is required"}, status=400)

        job_qs = AgentKVJob.objects.filter(id=job_id, organization_id=org_id).exclude(
            status__in=list(AgentKVJob.TERMINAL)
        )
        job = job_qs.first()
        if job is None:
            # Late report for a job that already reached a terminal state
            # (completed/failed/cancelled) -- a no-op, not an error.
            return Response({"ok": True, "noop": True})

        stages = dict(job.stages or {})
        entry = {"status": body["status"]}
        if "seconds" in body:
            entry["seconds"] = body["seconds"]
        entry.update(body.get("counters") or {})
        stages[body["stage"]] = entry

        updates = {"stages": stages, "stage": body["stage"]}
        if job.status in (JobStatus.PENDING, JobStatus.DISPATCHED):
            updates["status"] = JobStatus.RUNNING
        job_qs.update(**updates)
        return Response({"ok": True})


class FinalizeView(APIView):
    """Terminalize a job: write its result (on success) then mark it done.

    Idempotent: a job already in a terminal state short-circuits before any
    write -- ``write_result`` is only ever called for a job that is still
    non-terminal at read time, so a duplicate/late finalize call can never
    rewrite an already-written result. The concurrency slot is always
    released, in a ``finally``, on every path (success, duplicate no-op, or
    an exception raised while finalizing).
    """

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, job_id=None, **kwargs):
        body = request.data
        org_id = body.get("org_id")
        if not org_id:
            return Response({"detail": "org_id is required"}, status=400)

        job = AgentKVJob.objects.filter(id=job_id, organization_id=org_id).first()
        finalized = False
        try:
            if job is not None and job.status not in AgentKVJob.TERMINAL:
                if body.get("success"):
                    result_ref = write_result(
                        org_id, str(job_id), body.get("result") or {}
                    )
                    finalized = AgentKVJob.mark_terminal(
                        job_id,
                        org_id,
                        JobStatus.COMPLETED,
                        result_ref=result_ref,
                        usage_summary=body.get("usage_summary"),
                    )
                    if finalized:
                        job.status = JobStatus.COMPLETED
                else:
                    finalized = AgentKVJob.mark_terminal(
                        job_id,
                        org_id,
                        JobStatus.FAILED,
                        error=body.get("error") or "",
                    )
                    if finalized:
                        job.status = JobStatus.FAILED
        finally:
            AgentKVConcurrencyLimiter.release(org_id, str(job_id))

        return Response(
            {
                "finalized": finalized,
                "webhook_url": job.webhook_url if job else "",
                "status": job.status.lower() if job else "",
            }
        )
