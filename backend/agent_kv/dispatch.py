"""Executor dispatch glue (spec §5.3). One dispatch per job; UUID task_id."""

import logging
import uuid

from celery import signature
from django.utils import timezone
from unstract.sdk1.execution.context import ExecutionContext

from agent_kv.constants import EXECUTION_SOURCE, EXECUTOR_NAME, OPERATION_KV_EXTRACT
from agent_kv.models import JobStatus

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
            "max_pages": job.pages_total,
        },
    )
    cb_kwargs = {"callback_kwargs": {"job_id": str(job.id), "org_id": org_id}}
    try:
        _dispatcher().dispatch_with_callback(
            context,
            on_success=signature(
                "agent_kv_complete", kwargs=cb_kwargs, queue=CALLBACK_QUEUE
            ),
            on_error=signature("agent_kv_error", kwargs=cb_kwargs, queue=CALLBACK_QUEUE),
            task_id=str(job.task_id),
        )
    except Exception as e:
        raise DispatchError(str(e)) from e
    job.status = JobStatus.DISPATCHED
    job.dispatched_at = timezone.now()
    job.save(update_fields=["task_id", "status", "dispatched_at", "modified_at"])
