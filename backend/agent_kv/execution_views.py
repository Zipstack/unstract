import logging
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from plugins import get_plugin
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from agent_kv.constants import STAGE_NAMES_BY_EXTRACTOR
from agent_kv.dispatch import DispatchError, dispatch_cancelled_webhook, dispatch_job
from agent_kv.exceptions import (
    EngineUnavailable,
    JobNotFound,
    RateLimited,
    SubscriptionGateUnavailable,
)
from agent_kv.execution_serializers import SubmitSerializer
from agent_kv.execution_views_result import result_payload
from agent_kv.key_validator import AgentKVKeyValidator
from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter, check_key_rate
from agent_kv.storage import delete_job_files, stage_input
from unstract.agent_kv_schema.compile import SchemaError, compile_schema

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
    # `.get`, not a subscript. No row can hold an out-of-dict value today (the
    # sole creation site is serializer-validated and the migration backfills
    # "kv"), but a RETIRED extractor name with surviving rows would 500 every
    # `GET status` for those jobs while `GET result` kept working -- the result
    # payload keys by `job.extractor` without consulting this table at all. An
    # empty stage list degrades to "no stages reported", which is honest for an
    # extractor this build no longer knows how to describe.
    stage_names = STAGE_NAMES_BY_EXTRACTOR.get(job.extractor)
    if stage_names is None:
        logger.warning(
            "agent-kv job %s ran extractor %r, which has no stage list in "
            "STAGE_NAMES_BY_EXTRACTOR; reporting an empty stage array",
            job.id,
            job.extractor,
        )
        stage_names = []
    doc = {
        "job_id": str(job.id),
        # The JOB's state, not an extractor's: a job is not complete until every
        # extractor is, so this stays top level (spec §7.2).
        "status": job.status.lower(),
        # Stage names are extractor-specific (`qa`/`challenge`/`codegen` mean
        # nothing to the table extractor) and they ARE returned to clients, so
        # they are wire format and namespaced with everything else.
        "extractors": {
            job.extractor: {
                "stage": job.stage,
                "stages": [
                    {"name": name, **stages_json[name]}
                    for name in stage_names
                    if name in stages_json
                ],
            }
        },
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.dispatched_at.isoformat() if job.dispatched_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "pages_total": job.pages_total,
    }
    if job.status == JobStatus.FAILED:
        doc["error"] = job.error
    return doc


def _never_dispatched(job) -> bool:
    """True when this job never reached an executor, so no callback will come.

    Read from the row as it was BEFORE this request terminalized it. Both
    conditions are deliberate: `dispatched_at` is stamped by post-enqueue
    bookkeeping that can legitimately fail, and `status` is what the dispatcher
    advances -- a job with either marker set has, or may have, a running
    executor whose finalize callback owns the slot.
    """
    return job.dispatched_at is None and job.status == JobStatus.PENDING


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


def _subscription_denial(plugin, agent_kv_key, request) -> Response | None:
    """Subscription admission (§6.6), or ``None`` when the org may proceed.

    A submit dispatches paid work, so it is gated exactly as an API deployment
    execute is -- same policy, same 402 bodies -- via the cloud plugin's gate,
    which calls the very ``SubscriptionHelper`` that cloud's
    ``SubscriptionMiddleware`` calls.

    Why here and not in that middleware: it resolves the org from the URL
    (``/deployment/api/{org_name}/...``). Agent-KV's URL carries no org segment
    -- the org is inside the Bearer key -- so the middleware's
    ``get_organization_id`` returns None for these requests, finds no
    subscription row, and admits every one of them. The view is the first point
    where the org is actually known.

    ``organization.organization_id`` is the org SLUG -- the CharField
    ``Subscription.organization_id`` is keyed on, and what the deployment URL
    supplies as ``org_name``. NOT ``agent_kv_key.organization_id``, which is the
    Organization FK primary key: that matches no row, and the shared policy
    reads "no row" as "nothing to enforce", so the gate would silently admit
    everything while looking correctly wired.

    **Fails closed when the plugin exposes no gate.** This used to return None
    -- admit -- to tolerate a cloud build predating the gate. But the admitted
    request dispatches billable LLM and OCR work, and this route's URL carries
    no org segment, so ``SubscriptionMiddleware`` cannot catch it downstream
    either: a mixed deploy (this backend against a pre-gate cloud image) would
    run unmetered paid work with nothing anywhere enforcing entitlement.

    Refusing instead is the conservative read of a deployment that can spend
    money but cannot check whether it may. It surfaces as a 503 naming the
    cause, not a 402 -- the subscription was never evaluated, and reporting it
    as denied would send an operator to the billing system for what is an
    image-pairing problem.

    Raises:
        SubscriptionGateUnavailable: the engine plugin is installed but exposes
            no ``service_class``.
    """
    gate_factory = plugin.get("service_class")
    if not gate_factory:
        logger.error(
            "agent-kv: engine plugin exposes no subscription gate; refusing the "
            "submit rather than dispatching billable work unmetered"
        )
        raise SubscriptionGateUnavailable()
    return gate_factory().check(agent_kv_key.organization.organization_id, request)


def _dispatch_or_fail(job, org_id: str, entry: dict, options: dict) -> Response | None:
    """Dispatch the job, or return the failure response. ``None`` means sent.

    Both failure paths terminalize the job and release the concurrency slot.
    The bare ``except`` is belt-and-braces: ``dispatch_job`` wraps its own
    internal failures as ``DispatchError``, but nothing here may rely on that
    alone -- any other exception must still terminalize and release rather than
    escape as an unhandled 500 with the slot still held.
    """
    try:
        dispatch_job(job, extractor=entry["name"], schema=entry["keys"], options=options)
    except DispatchError:
        logger.exception("agent-kv dispatch failed for job %s", job.id)
    except Exception:
        logger.exception("agent-kv dispatch raised unexpectedly for job %s", job.id)
    else:
        return None
    return _fail_job_response(
        job, org_id, "Job could not be dispatched; nothing was billed.", job_saved=True
    )


def _sync_wait_response(job, wait: float) -> Response | None:
    """Poll until the job is terminal or ``wait`` elapses (§7.1 sync mode).

    Returns the full result payload if it terminalized in time, else ``None``
    so the caller falls through to the normal 202 handshake.
    """
    if not wait:
        return None
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        job.refresh_from_db()
        if job.status in AgentKVJob.TERMINAL:
            from agent_kv.execution_views_result import result_payload

            return Response(result_payload(job), status=200)
        time.sleep(1)
    return None


class SubmitView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, agent_kv_key=None, **kwargs):
        plugin = get_plugin("agent_kv")
        if not plugin:
            raise EngineUnavailable()
        if not check_key_rate(str(agent_kv_key.id)):
            raise RateLimited()

        denied = _subscription_denial(plugin, agent_kv_key, request)
        if denied is not None:
            return denied

        data = request.data.copy()
        part = data.get("extractors")
        if hasattr(part, "read"):  # `extractors` uploaded as a file part (§7.1)
            # Bounded read. The size cap lives in `validate_extractors`, i.e.
            # AFTER this point -- and `DATA_UPLOAD_MAX_MEMORY_SIZE` excludes
            # file-typed parts, so a 500 MB `extractors` part was materialised
            # in full (plus up to 4x that again for the `str`) before being
            # rejected at 256 KiB. One such request per worker process OOMs the
            # pod, which makes it a cheap denial of service.
            #
            # Read one byte past the cap: enough to know it is over without
            # ever holding more than the cap plus one.
            limit = settings.AGENT_KV_MAX_SCHEMA_BYTES
            raw = part.read(limit + 1)
            if len(raw) > limit:
                raise ValidationError(
                    {"extractors": f"extractors payload exceeds {limit} bytes"}
                )
            try:
                # `errors="strict"`, not "replace". A latin-1 key name used to
                # decode to U+FFFD and then compile cleanly, so a malformed
                # payload became a job that ran against a schema the caller
                # never wrote.
                data["extractors"] = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise ValidationError(
                    {"extractors": "extractors must be valid UTF-8"}
                ) from None
        serializer = SubmitSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        org_id = str(agent_kv_key.organization_id)

        job = AgentKVJob(
            api_key=agent_kv_key,
            organization_id=agent_kv_key.organization_id,
            extractor=v["extractors"][0]["name"],
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
            logger.exception("agent-kv staging/save failed for job %s", job.id)
            # Delete the staged object before responding. If `stage_input`
            # succeeded and `job.save()` then raised, the upload exists with no
            # row to carry its ref -- and `run_ttl_cleanup` selects candidates
            # from `AgentKVJob` rows, so an object with no row is structurally
            # unreachable by every cleanup path there is. It would sit in the
            # bucket forever, holding customer data nobody can find or delete.
            if job.input_ref:
                try:
                    delete_job_files(job)
                except Exception:
                    logger.exception(
                        "agent-kv: could not remove the staged input for failed "
                        "submit %s; it is now orphaned (no job row carries its "
                        "ref, so TTL cleanup cannot reach it)",
                        job.id,
                    )
            return _fail_job_response(
                job,
                org_id,
                "Job could not be accepted; nothing was billed.",
                job_saved=job_saved,
            )

        # Unpack the single extractor entry into the FROZEN OSS<->cloud
        # executor_params contract (`schema` + `options`). The wire format
        # changed at the API edge only: the engine still receives exactly the
        # option names it always did, so no cloud change is required.
        entry = v["extractors"][0]
        options = dict(entry["options"])
        # Job-level, but the engine reads them from `options` (§7.1: the page
        # range drives the shared OCR pass, so it cannot be per-extractor).
        options["page_start"] = v["page_start"]
        options["page_end"] = v["page_end"]

        failed = _dispatch_or_fail(job, org_id, entry, options)
        if failed is not None:
            return failed

        inline = _sync_wait_response(job, v["timeout"])
        if inline is not None:
            return inline

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
            won = AgentKVJob.mark_terminal(
                job.id, job.organization_id, JobStatus.CANCELLED
            )
            if won:
                # Release the concurrency slot ONLY for a job that was never
                # dispatched.
                #
                # The slot is taken at submit and released by
                # `_fail_job_response`, the finalize callback and the sweep. A
                # job cancelled BEFORE dispatch gets no finalize callback, and
                # the sweep's phase-1 only targets PENDING, never CANCELLED --
                # so without this release its slot would leak until the 6h TTL.
                # That is what this release is for, and all it is for.
                #
                # It used to fire for ANY non-terminal job, including one
                # mid-run. Nothing revokes a running executor -- `job.task_id`
                # is written at dispatch and never read again -- so the engine
                # kept running, kept calling LLMs and kept billing while its
                # slot was handed to the next submit. Submit-then-cancel in a
                # loop therefore ran arbitrarily many concurrent extractions
                # against a ceiling of `AGENT_KV_CONCURRENT_LIMIT`, all paid for.
                #
                # Narrowing loses nothing: a mid-run cancel's slot is released
                # by `FinalizeView`'s `finally` when the executor's callback
                # lands, and `release()` is idempotent (zrem).
                #
                # Guarded on `won` so a lost race (a concurrent cancel or
                # finalize terminalized it first) does not release a slot that
                # the winner is still accounting for.
                if _never_dispatched(job):
                    AgentKVConcurrencyLimiter.release(
                        str(job.organization_id), str(job.id)
                    )
                # This request owns the terminal notification: no fresh finalize
                # can follow a cancel that won, so nothing else will send it.
                dispatch_cancelled_webhook(job)
            else:
                # Lost the race: a finalize or cancel terminalized this job
                # between our read above and the guarded UPDATE. `job` is now
                # STALE, and `result_ref` is the field that matters -- a winning
                # finalize has just written one.
                #
                # Without this refresh the cleanup below runs against the stale
                # copy, where `result_ref` is still "". `delete_job_files`
                # reports an already-empty ref as "cleared" (nothing to delete),
                # so the save then writes "" OVER the winner's real ref. The job
                # stays COMPLETED, its result 404s (`JobResultView` treats
                # COMPLETED-without-a-ref as swept), and the object is orphaned
                # in the bucket with nothing left pointing at it -- TTL cleanup
                # selects on `result_ref > ""`, so a blanked row never comes
                # back. Deleting is still the caller's intent; it just has to
                # act on the refs that actually exist now.
                job.refresh_from_db()
        # Blank only the refs whose files are confirmed gone, so a ref whose
        # delete failed survives as the handle TTL cleanup retries from. 204
        # either way: the job IS terminal and the caller's intent is recorded,
        # and a sync 5xx here would only invite a retry of a DELETE that already
        # did everything it could.
        cleared = delete_job_files(job)
        if cleared:
            for field in cleared:
                setattr(job, field, "")
            job.save(update_fields=cleared)
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
            # Release the concurrency slot ONLY for a job that was never
            # dispatched.
            #
            # The slot is taken at submit and released by
            # `_fail_job_response`, the finalize callback and the sweep. A
            # job cancelled BEFORE dispatch gets no finalize callback, and
            # the sweep's phase-1 only targets PENDING, never CANCELLED --
            # so without this release its slot would leak until the 6h TTL.
            # That is what this release is for, and all it is for.
            #
            # It used to fire for ANY non-terminal job, including one
            # mid-run. Nothing revokes a running executor -- `job.task_id`
            # is written at dispatch and never read again -- so the engine
            # kept running, kept calling LLMs and kept billing while its
            # slot was handed to the next submit. Submit-then-cancel in a
            # loop therefore ran arbitrarily many concurrent extractions
            # against a ceiling of `AGENT_KV_CONCURRENT_LIMIT`, all paid for.
            #
            # Narrowing loses nothing: a mid-run cancel's slot is released
            # by `FinalizeView`'s `finally` when the executor's callback
            # lands, and `release()` is idempotent (zrem).
            if _never_dispatched(job):
                AgentKVConcurrencyLimiter.release(str(job.organization_id), str(job.id))
            # Docs §8 promises a terminal notification, and cancellation never
            # reaches finalize -- so this path has to send it. Guarded on `won`
            # so a cancel that LOST leaves the notification to the finalize that
            # beat it, and the caller is told exactly once.
            dispatch_cancelled_webhook(job)
            return Response({"status": "cancelled"}, status=200)
        # Lowercased for cross-endpoint consistency (spec §7.2).
        return Response({"status": job.status.lower()}, status=409)
