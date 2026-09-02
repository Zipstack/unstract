import logging
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from plugins import get_plugin
from rest_framework.response import Response
from rest_framework.views import APIView
from unstract.agent_kv_schema.compile import SchemaError, compile_schema

from agent_kv.constants import STAGE_NAMES
from agent_kv.dispatch import DispatchError, dispatch_job
from agent_kv.exceptions import EngineUnavailable, JobNotFound, RateLimited
from agent_kv.execution_serializers import SubmitSerializer
from agent_kv.execution_views_result import result_payload
from agent_kv.key_validator import AgentKVKeyValidator
from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter, check_key_rate
from agent_kv.storage import delete_job_files, stage_input

logger = logging.getLogger(__name__)


def _get_job(agent_kv_key, job_id):
    """Org-scoped lookup used by every job-scoped endpoint (spec §5.4).

    Unknown job_id and a job that belongs to a different org must be
    indistinguishable to the caller, so both funnel through the same
    ``DoesNotExist`` -> ``JobNotFound`` (404) path.
    """
    try:
        return AgentKVJob.objects.get(
            id=job_id, organization_id=agent_kv_key.organization_id
        )
    except AgentKVJob.DoesNotExist:
        raise JobNotFound()


def _status_document(job) -> dict:
    """Build the status document per spec §7.2."""
    stages_json = job.stages or {}
    doc = {
        "job_id": str(job.id),
        "status": job.status.lower(),
        "stage": job.stage,
        "stages": [
            {"name": name, **stages_json[name]}
            for name in STAGE_NAMES
            if name in stages_json
        ],
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.dispatched_at.isoformat() if job.dispatched_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "pages_total": job.pages_total,
    }
    if job.status == JobStatus.FAILED:
        doc["error"] = job.error
    return doc


def _fail_job_response(job, org_id: str, message: str, *, job_saved: bool) -> Response:
    """Shared cleanup for any post-acquire submit failure (spec §5.3/§5.4).

    Always releases the concurrency slot acquired earlier in the request.
    Only calls ``mark_terminal`` when a job row may actually exist — calling
    it against a job_id with no row is harmless (the guarded UPDATE just
    matches zero rows), but ``job_saved`` keeps the write guard's intent
    (only terminalize rows that exist) obvious at the call site.
    """
    if job_saved:
        AgentKVJob.mark_terminal(
            job.id, job.organization_id, JobStatus.FAILED, error=message
        )
    AgentKVConcurrencyLimiter.release(org_id, str(job.id))
    return Response(
        {"job_id": str(job.id), "status": JobStatus.FAILED.lower(), "error": message},
        status=500,
    )


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

        job_saved = False
        try:
            job.input_ref = stage_input(org_id, str(job.id), v["file"])
            job.save()
            job_saved = True
        except Exception:
            logger.error("agent-kv staging/save failed for job %s", job.id, exc_info=True)
            return _fail_job_response(
                job,
                org_id,
                "Job could not be accepted; nothing was billed.",
                job_saved=job_saved,
            )

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
            return _fail_job_response(
                job,
                org_id,
                "Job could not be dispatched; nothing was billed.",
                job_saved=True,
            )
        except Exception:
            # Belt-and-braces: dispatch_job wraps its own internal failures
            # as DispatchError, but nothing here may rely on that alone —
            # any other exception must still terminalize the job and
            # release the slot rather than escape as an unhandled 500.
            logger.error(
                "agent-kv dispatch raised unexpectedly for job %s",
                job.id,
                exc_info=True,
            )
            return _fail_job_response(
                job,
                org_id,
                "Job could not be dispatched; nothing was billed.",
                job_saved=True,
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
                # Lowercased for cross-endpoint consistency (spec §7.2) -- the
                # 202 body used to leak the raw uppercase status.
                "status": job.status.lower(),
                "status_url": f"/{settings.AGENT_KV_PATH_PREFIX}/{job.id}",
                "created_at": job.created_at.isoformat(),
            },
            status=202,
        )


class ValidateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, agent_kv_key=None, **kwargs):
        if not check_key_rate(str(agent_kv_key.id)):
            raise RateLimited()
        spec = request.data.get("keys")
        if spec is None:
            return Response({"detail": "body must include 'keys'"}, status=400)
        try:
            compiled = compile_schema(spec)
        except SchemaError as e:
            return Response({"valid": False, "error": str(e)}, status=200)
        return Response(
            {
                "valid": True,
                "leaves": len(compiled.key_specs),
                "arrays": len(compiled.array_specs),
                "constraints": len(compiled.constraints),
            },
            status=200,
        )


class JobStatusView(APIView):
    """GET status document; DELETE purges the job's staged/result files.

    DELETE is merged onto this class (rather than a standalone
    ``JobDeleteView``) because both share the ``<uuid:job_id>`` URL — Django
    matches a URL pattern once per request regardless of HTTP method, so two
    separate ``path()`` entries for the same literal path can't coexist.
    ``JobDeleteView`` below is kept as a name alias for this same class.
    """

    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def get(self, request, *args, job_id=None, agent_kv_key=None, **kwargs):
        job = _get_job(agent_kv_key, job_id)
        return Response(_status_document(job), status=200)

    @AgentKVKeyValidator.validate_api_key
    def delete(self, request, *args, job_id=None, agent_kv_key=None, **kwargs):
        job = _get_job(agent_kv_key, job_id)
        if job.status not in AgentKVJob.TERMINAL:
            # Cancel BEFORE deleting files: a still-running job would
            # otherwise keep running after its files are gone, and its
            # eventual finalize call would write a fresh result_ref onto a
            # job the caller already asked to delete -- resurrecting a
            # result they explicitly discarded. Terminalizing first closes
            # that window; a finalize call that still lands late loses the
            # terminal-state guard and, on the success path, cleans up its
            # own now-orphaned write (FinalizeView, storage.delete_result_file).
            AgentKVJob.mark_terminal(job.id, job.organization_id, JobStatus.CANCELLED)
        delete_job_files(job)
        job.input_ref = ""
        job.result_ref = ""
        job.save(update_fields=["input_ref", "result_ref"])
        return Response(status=204)


# Alias kept for a descriptive import name; there is no separate URL route
# (see the JobStatusView docstring above) — DELETE rides JobStatusView's URL.
JobDeleteView = JobStatusView


class JobResultView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def get(self, request, *args, job_id=None, agent_kv_key=None, **kwargs):
        job = _get_job(agent_kv_key, job_id)
        if job.status not in AgentKVJob.TERMINAL:
            return Response({"status": job.status.lower()}, status=409)
        # A job's row outlives its result by design (audit trail after TTL
        # cleanup blanks the refs) -- expired or a COMPLETED job whose
        # result was already swept both mean "nothing left to serve".
        if (job.expires_at and job.expires_at < timezone.now()) or (
            job.status == JobStatus.COMPLETED and not job.result_ref
        ):
            raise JobNotFound()
        return Response(result_payload(job), status=200)


class JobCancelView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, job_id=None, agent_kv_key=None, **kwargs):
        job = _get_job(agent_kv_key, job_id)
        won = AgentKVJob.mark_terminal(job.id, job.organization_id, JobStatus.CANCELLED)
        if won:
            # The slot is acquired at submit and released by _fail_job_response,
            # the finalize callback, and the sweep. A job cancelled BEFORE
            # dispatch gets no finalize callback, and the sweep's phase-1 only
            # targets PENDING (not CANCELLED) -- so without this release its
            # slot would leak until the 6h TTL (pre-Greptile important #4).
            # release() is idempotent (zrem), so a later finalize-callback
            # release on a cancel-mid-run is harmless.
            AgentKVConcurrencyLimiter.release(str(job.organization_id), str(job.id))
            return Response({"status": "cancelled"}, status=200)
        # Lowercased for cross-endpoint consistency (spec §7.2).
        return Response({"status": job.status.lower()}, status=409)
