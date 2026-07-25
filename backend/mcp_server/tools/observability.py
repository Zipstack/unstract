"""Read-only tools for execution history, usage and workflow structure.

Every response here is built **field by field from named model attributes**.
That is a security boundary, not a style preference: several of this project's
serializers return decrypted credentials in their normal output — connector
metadata carries database passwords and object-store keys, adapter metadata
carries provider API keys — and a workflow endpoint references a connector
instance. Passing a model through ``serializer.data``, ``model_to_dict`` or a
``**`` splat would pipe those secrets into an LLM's context and defeat the
whole exclusion list in this app's README.

So: name every field you return. ``test_no_credentials_in_tool_output``
enforces this across the whole registry.
"""

import logging
import re
from typing import Any

from usage_v2.models import Usage
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from mcp_server.context import PlatformMCPContext
from mcp_server.exceptions import MCPToolError

logger = logging.getLogger(__name__)

# Executions are the highest-cardinality thing here, and an agent asking "what
# happened" wants the recent tail rather than the archive.
EXECUTION_LIMIT = 25
LOG_LIMIT = 100


# Error text from a failed execution is one of the few places a secret can
# reach an agent without any tool asking for it: a connector that fails to
# connect may report the connection string it tried, and a provider client may
# echo the key it authenticated with. These patterns catch the common shapes.
_REDACTED = "[REDACTED]"

# Each entry is (pattern, replacement). The replacement keeps the surrounding
# context — the key name, the URL prefix — so the message stays diagnosable
# while the value itself is gone.
_SECRET_PATTERNS = (
    # Bearer tokens first: "Authorization: Bearer <token>" would otherwise be
    # consumed by the key=value rule below, which would mask the word "Bearer"
    # and leave the token itself in place.
    (
        re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._\-]{8,})"),
        rf"\1{_REDACTED}",
    ),
    # key=value / key: value, where the key looks credential-ish. Stops at
    # whitespace, quote or delimiter so the rest of the message survives.
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|secret_access_key|access_key|"
            r"api[_-]?key|token|authorization|credential)"
            r"(\s*[=:]\s*)"
            r"([^\s,;'\"&)}\]]+)"
        ),
        rf"\1\2{_REDACTED}",
    ),
    # Credentials embedded in a URL: scheme://user:secret@host
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@]+)(@)"),
        rf"\1{_REDACTED}\3",
    ),
)


def redact_secrets(text: str | None) -> str | None:
    """Mask credential-shaped substrings in free-form text.

    Applied to every error message these tools return. Execution errors are one
    of the few places a secret reaches an agent without any tool asking for it:
    a connector that fails to connect may report the connection string it
    tried, and a provider client may echo the key it authenticated with.

    This is a safety net, not a guarantee — it cannot recognise a secret that
    looks like ordinary prose — so it complements the rule that structured
    fields are named explicitly rather than replacing it.
    """
    if not text:
        return text

    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _org_workflow_ids(context: PlatformMCPContext) -> list[Any]:
    """Workflow ids the caller may see, for scoping execution queries.

    WorkflowExecution has no ``for_user`` manager, so visibility is derived
    from the workflows the caller can reach rather than assumed.
    """
    return list(Workflow.objects.for_user(context.user).values_list("id", flat=True))


def list_executions_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": (
                    "Optional UUID to show executions of one workflow only. "
                    "Omit for the organization's most recent executions."
                ),
            },
            "status": {
                "type": "string",
                "description": (
                    "Optional status filter, e.g. COMPLETED, ERROR, EXECUTING, PENDING."
                ),
            },
        },
        "required": [],
    }


def list_executions(
    context: PlatformMCPContext,
    workflow_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """List recent workflow executions, newest first.

    This is the tool for "why did that fail" and "did it run" — the questions
    an agent actually has after triggering work.
    """
    visible = _org_workflow_ids(context)
    queryset = WorkflowExecution.objects.filter(workflow_id__in=visible)

    if workflow_id:
        if not any(str(wid) == str(workflow_id) for wid in visible):
            raise MCPToolError(
                f"No workflow with id '{workflow_id}' in organization "
                f"'{context.org_name}'. Call listWorkflows for valid ids."
            )
        queryset = queryset.filter(workflow_id=workflow_id)
    if status:
        queryset = queryset.filter(status=status.upper())

    queryset = queryset.order_by("-created_at")
    total = queryset.count()
    rows = queryset[:EXECUTION_LIMIT]

    return {
        "count": total,
        "showing": min(total, EXECUTION_LIMIT),
        "executions": [
            {
                "id": str(row.id),
                "workflow_id": str(row.workflow_id),
                "pipeline_id": str(row.pipeline_id) if row.pipeline_id else None,
                "status": row.status,
                "execution_mode": row.execution_mode,
                "total_files": row.total_files,
                "successful_files": row.successful_files,
                "failed_files": row.failed_files,
                # Truncated: an error message can be a full stack trace, and a
                # page of them would crowd out everything else.
                "error_message": redact_secrets((row.error_message or "")[:500]) or None,
                "attempts": row.attempts,
                "execution_time_seconds": row.execution_time,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        **(
            {
                "truncated": True,
                "note": (
                    f"Showing the {EXECUTION_LIMIT} most recent of {total}. "
                    "Filter by workflow_id or status to narrow."
                ),
            }
            if total > EXECUTION_LIMIT
            else {}
        ),
    }


def get_execution_detail_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "execution_id": {
                "type": "string",
                "description": "UUID of the execution, from listExecutions.",
            },
        },
        "required": ["execution_id"],
    }


def get_execution_detail(
    context: PlatformMCPContext, execution_id: str
) -> dict[str, Any]:
    """Per-file detail for one execution — which files failed, and why."""
    visible = _org_workflow_ids(context)
    execution = WorkflowExecution.objects.filter(
        id=execution_id, workflow_id__in=visible
    ).first()
    if execution is None:
        raise MCPToolError(
            f"No execution with id '{execution_id}' in organization "
            f"'{context.org_name}'. Call listExecutions for valid ids."
        )

    files = []
    try:
        for fe in execution.file_executions.all()[:LOG_LIMIT]:
            files.append(
                {
                    "id": str(fe.id),
                    "file_name": fe.file_name,
                    "status": fe.status,
                    "error": redact_secrets((fe.execution_error or "")[:500]) or None,
                }
            )
    except Exception as error:  # pragma: no cover - defensive
        logger.warning(f"Could not load file executions for '{execution_id}': {error}")

    return {
        "id": str(execution.id),
        "workflow_id": str(execution.workflow_id),
        "status": execution.status,
        "total_files": execution.total_files,
        "successful_files": execution.successful_files,
        "failed_files": execution.failed_files,
        "error_message": redact_secrets((execution.error_message or "")[:1000]) or None,
        "execution_time_seconds": execution.execution_time,
        "created_at": execution.created_at,
        "files": files,
    }


def get_usage_summary_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


def get_usage_summary(context: PlatformMCPContext) -> dict[str, Any]:
    """Aggregate token and cost usage for the organization.

    Aggregated in the database rather than by pulling rows: a busy
    organization has far more usage records than belong in an agent's context,
    and the totals are what the question is actually about.
    """
    from django.db.models import Count, Sum

    totals = Usage.objects.aggregate(
        records=Count("id"),
        prompt_tokens=Sum("prompt_tokens"),
        completion_tokens=Sum("completion_tokens"),
        total_tokens=Sum("total_tokens"),
        embedding_tokens=Sum("embedding_tokens"),
        cost_in_dollars=Sum("cost_in_dollars"),
    )

    return {
        "organization": context.org_name,
        "records": totals["records"] or 0,
        "prompt_tokens": totals["prompt_tokens"] or 0,
        "completion_tokens": totals["completion_tokens"] or 0,
        "total_tokens": totals["total_tokens"] or 0,
        "embedding_tokens": totals["embedding_tokens"] or 0,
        "cost_in_dollars": float(totals["cost_in_dollars"] or 0),
        "note": (
            "Totals across all recorded usage for this organization. This is "
            "historical accounting, not a spending limit."
        ),
    }


def list_tool_instances_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the workflow, from listWorkflows.",
            },
        },
        "required": ["workflow_id"],
    }


def list_tool_instances(context: PlatformMCPContext, workflow_id: str) -> dict[str, Any]:
    """List the tool steps inside a workflow, in execution order.

    Tool settings are omitted deliberately: they are free-form JSON that can
    carry adapter ids and, in some tools, credential-shaped values. The step
    order and identity answer "what does this workflow do" without that risk.
    """
    from tool_instance_v2.models import ToolInstance

    workflow = Workflow.objects.for_user(context.user).filter(id=workflow_id).first()
    if workflow is None:
        raise MCPToolError(
            f"No workflow with id '{workflow_id}' in organization "
            f"'{context.org_name}'. Call listWorkflows for valid ids."
        )

    rows = ToolInstance.objects.filter(workflow=workflow).order_by("step")

    return {
        "workflow_id": str(workflow.id),
        "workflow_name": workflow.workflow_name,
        "tool_instances": [
            {
                "id": str(row.id),
                "tool_id": row.tool_id,
                "step": row.step,
            }
            for row in rows
        ],
        "note": (
            "Tool settings are not exposed — they can reference adapters and "
            "credential-shaped values. Use the Unstract UI to inspect them."
        ),
    }


def list_tags(context: PlatformMCPContext) -> dict[str, Any]:
    """List the organization's execution tags."""
    from tags.models import Tag

    queryset = Tag.objects.all().order_by("name")
    total = queryset.count()
    rows = queryset[:100]

    return {
        "count": total,
        "tags": [
            {"id": str(row.id), "name": row.name, "description": row.description or None}
            for row in rows
        ],
    }


def get_workflow_endpoints_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the workflow, from listWorkflows.",
            },
        },
        "required": ["workflow_id"],
    }


def get_workflow_endpoints(
    context: PlatformMCPContext, workflow_id: str
) -> dict[str, Any]:
    """Describe a workflow's source and destination wiring.

    Returns the *shape* of the connection — endpoint type, connection type, and
    the connector's name — and deliberately never its configuration. A
    connector instance holds decrypted credentials in ``connector_metadata``,
    so only named, non-secret attributes are read here. Do not extend this to
    return ``configuration`` or ``connector_metadata``.
    """
    workflow = Workflow.objects.for_user(context.user).filter(id=workflow_id).first()
    if workflow is None:
        raise MCPToolError(
            f"No workflow with id '{workflow_id}' in organization "
            f"'{context.org_name}'. Call listWorkflows for valid ids."
        )

    endpoints = []
    for endpoint in WorkflowEndpoint.objects.filter(workflow=workflow):
        connector = getattr(endpoint, "connector_instance", None)
        endpoints.append(
            {
                "id": str(endpoint.id),
                "endpoint_type": endpoint.endpoint_type,
                "connection_type": endpoint.connection_type,
                # Name and id only. The connector's metadata is credential
                # material and must not appear here.
                "connector_name": getattr(connector, "connector_name", None),
                "connector_id": str(connector.id) if connector else None,
                "is_configured": bool(endpoint.configuration),
            }
        )

    return {
        "workflow_id": str(workflow.id),
        "workflow_name": workflow.workflow_name,
        "endpoints": endpoints,
        "note": (
            "Connector credentials and endpoint configuration are deliberately "
            "not exposed. Use the Unstract UI to inspect or change them."
        ),
    }
