import logging
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from plugins import get_plugin
from rest_framework.response import Response
from rest_framework.views import APIView

from agent_kv.dispatch import DispatchError, dispatch_job
from agent_kv.exceptions import EngineUnavailable, RateLimited
from agent_kv.execution_serializers import SubmitSerializer
from agent_kv.key_validator import AgentKVKeyValidator
from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter, check_key_rate
from agent_kv.storage import stage_input

logger = logging.getLogger(__name__)


class SubmitView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, agent_kv_key=None, **kwargs):
        if not get_plugin("agent_kv"):
            raise EngineUnavailable()
        if not check_key_rate(str(agent_kv_key.id)):
            raise RateLimited()

        data = request.data.copy()
        keys_part = data.get("keys")
        if hasattr(keys_part, "read"):  # `keys` uploaded as a file part (§7.1)
            data["keys"] = keys_part.read().decode("utf-8", errors="replace")
        serializer = SubmitSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        org_id = str(agent_kv_key.organization_id)

        job = AgentKVJob(
            api_key=agent_kv_key,
            organization_id=agent_kv_key.organization_id,
            pages_total=serializer.pages_total,
            tags=v["tags"],
            custom_data=v["custom_data"],
            webhook_url=v["webhook_url"],
            expires_at=timezone.now() + timedelta(days=settings.AGENT_KV_RESULT_TTL_DAYS),
        )
        if not AgentKVConcurrencyLimiter.check_and_acquire(org_id, str(job.id)):
            raise RateLimited("Concurrent job limit reached")

        job.input_ref = stage_input(org_id, str(job.id), v["file"])
        job.save()

        options = {
            k: v[k]
            for k in (
                "qa",
                "challenge",
                "extraction_mode",
                "structured_output",
                "page_start",
                "page_end",
                "document_class",
                "key_notes",
                "calculations",
            )
        }
        try:
            dispatch_job(job, schema=v["keys"], options=options)
        except DispatchError:
            logger.error("agent-kv dispatch failed for job %s", job.id, exc_info=True)
            AgentKVJob.mark_terminal(
                job.id,
                job.organization_id,
                JobStatus.FAILED,
                error="Job could not be dispatched; nothing was billed.",
            )
            AgentKVConcurrencyLimiter.release(org_id, str(job.id))
            return Response(
                {
                    "job_id": str(job.id),
                    "status": JobStatus.FAILED,
                    "error": "Job could not be dispatched; nothing was billed.",
                },
                status=500,
            )

        wait = v["timeout"]
        if wait:
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                job.refresh_from_db()
                if job.status in AgentKVJob.TERMINAL:
                    from agent_kv.execution_views_result import result_payload

                    return Response(result_payload(job), status=200)
                time.sleep(1)

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "status_url": f"/{settings.AGENT_KV_PATH_PREFIX}/{job.id}",
                "created_at": job.created_at.isoformat(),
            },
            status=202,
        )
