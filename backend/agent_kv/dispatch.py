"""Executor dispatch glue (spec §5.3). One dispatch per job; UUID task_id."""

import logging
import uuid

from celery import signature
from django.conf import settings
from django.utils import timezone
from unstract.sdk1.execution.context import ExecutionContext

from agent_kv.constants import EXECUTION_SOURCE, EXECUTOR_NAME, OPERATION_KV_EXTRACT
from agent_kv.models import AgentKVJob, JobStatus

logger = logging.getLogger(__name__)

CALLBACK_QUEUE = "agent_kv_callback"


class DispatchError(Exception):
    """Enqueue failed; the caller terminalizes the job (spec §5.3)."""


def _dispatcher():
    from backend.celery_service import app as celery_app
    from pg_queue.executor_rpc import get_executor_dispatcher

    return get_executor_dispatcher(celery_app=celery_app)


def _platform_api_key(org_id: str) -> str:
    # Lazy import: avoids Django app registry init order (mirrors
    # PromptStudioHelper._get_platform_api_key).
    from platform_settings_v2.platform_auth_service import (
        PlatformAuthenticationService,
    )

    platform_key = PlatformAuthenticationService.get_active_platform_key(org_id)
    if not platform_key:
        raise DispatchError(f"No active platform key for org {org_id}")
    return str(platform_key.key)


def dispatch_job(job, *, schema: dict, options: dict) -> None:
    org_id = str(job.organization_id)
    # Everything that can fail — platform-key lookup, context construction,
    # and the enqueue call itself — lives inside this try so no internal
    # failure (e.g. a transient DB error resolving the platform key) can
    # escape as a raw, uncaught exception. Only the post-success bookkeeping
    # below runs outside it.
    try:
        job.task_id = uuid.uuid4()
        context = ExecutionContext(
            executor_name=EXECUTOR_NAME,
            operation=OPERATION_KV_EXTRACT,
            run_id=str(job.id),
            execution_source=EXECUTION_SOURCE,
            organization_id=org_id,
            executor_params={
                "job_id": str(job.id),
                "input_ref": job.input_ref,
                "schema": schema,
                "options": options,
                "platform_api_key": _platform_api_key(org_id),
                # The CAP the engine must enforce (spec §6.1/§6.6), not the
                # measured count -- job.pages_total is None for Excel (no
                # pre-OCR page concept), which would otherwise leave the
                # engine with nothing to check the post-OCR virtual-page cap
                # against. The measured count still rides along separately.
                "max_pages": settings.AGENT_KV_MAX_PAGES,
                "pages_total": job.pages_total,
            },
        )
        cb_kwargs = {"callback_kwargs": {"job_id": str(job.id), "org_id": org_id}}
        _dispatcher().dispatch_with_callback(
            context,
            on_success=signature(
                "agent_kv_complete", kwargs=cb_kwargs, queue=CALLBACK_QUEUE
            ),
            on_error=signature("agent_kv_error", kwargs=cb_kwargs, queue=CALLBACK_QUEUE),
            task_id=str(job.task_id),
        )
    except DispatchError:
        raise
    except Exception as e:
        raise DispatchError(str(e)) from e
    job.status = JobStatus.DISPATCHED
    job.dispatched_at = timezone.now()
    # Guarded queryset UPDATE, not job.save(): a plain save would blindly
    # overwrite whatever status this job already raced to. Concretely: the
    # executor can fail (or the job be cancelled) essentially instantly
    # after enqueue, and its finalize callback can land -- marking the row
    # FAILED/CANCELLED -- before this post-enqueue bookkeeping runs. An
    # unconditional save() here would rewrite that terminal status back to
    # DISPATCHED, un-terminalizing the job forever (nothing else ever
    # revisits a DISPATCHED row). Only a still-PENDING row is advanced; a
    # row this UPDATE doesn't match is left exactly as the winning writer
    # left it. `modified_at` is stamped automatically by
    # BaseModelQuerySet.update() (utils/models/base_model.py).
    AgentKVJob.objects.filter(id=job.id, status=JobStatus.PENDING).update(
        task_id=job.task_id,
        status=job.status,
        dispatched_at=job.dispatched_at,
    )
