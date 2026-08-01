"""Tools for the organization-scoped MCP server.

Every query goes through the model's own ``for_user`` manager rather than a raw
queryset, so the platform's sharing and visibility rules apply here exactly as
they do in the UI — this app does not get its own opinion about who may see or
touch what.

One caveat those managers impose, which the tool descriptions state plainly: a
platform key resolves to a service account, and ``for_user`` short-circuits to
"everything in the organization" for service accounts. These tools therefore
reach all org resources regardless of the role the key was created with — for
the write tools below that means they can modify anything in the organization,
not merely what one user could.

Write tools are authorized per tool by the view, using the platform key's
existing permission tier — see ``MCPTool.required_method``.
"""

import logging
import uuid
from typing import Any

from api_v2.models import APIDeployment
from pipeline_v2.models import Pipeline
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from workflow_manager.workflow_v2.models.workflow import Workflow

from mcp_server import spend_guard
from mcp_server.context import PlatformMCPContext
from mcp_server.exceptions import MCPToolError

logger = logging.getLogger(__name__)

# Listings are bounded so a large organization cannot blow up an agent's
# context window. Chosen to comfortably cover real orgs while still being a
# ceiling; tools report when they hit it rather than truncating silently.
LIST_LIMIT = 100


def no_args_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


# Every write tool repeats this, because the tool description is the prompt the
# agent reads before deciding to act — and the blast radius of a write is wider
# than the caveat's usual home in whoami.
_ORG_WIDE_WARNING = (
    "This credential is a service account and can modify ANY resource in the "
    "organization, not only those shared with a particular user. Confirm you "
    "have the right target before calling."
)


def valid_uuid(value: str, field: str, hint: str) -> str:
    """Reject a malformed id before it reaches a UUID-typed ORM filter.

    Filtering a UUID column by an unparseable string raises Django's
    ``ValidationError`` from the field itself, *before* the ``is None`` check
    each call site writes — so the agent gets a generic failure instead of the
    actionable message the site already prepared, and on the preflight path it
    escaped the JSON-RPC envelope entirely.

    Returns the value unchanged so it can be used inline.
    """
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as error:
        raise MCPToolError(
            f"'{value}' is not a valid {field}. Expected a UUID. {hint}"
        ) from error
    return value


def _truncation_note(shown: int, total: int) -> dict[str, Any]:
    """Describe a capped listing, or nothing when it was complete.

    Silent truncation would read to an agent as "this is everything", which is
    exactly the sort of wrong premise it would then build on.
    """
    if total <= shown:
        return {}
    return {
        "truncated": True,
        "note": (
            f"Showing {shown} of {total}. Narrow the question or use the "
            "Unstract UI to see the rest."
        ),
    }


def platform_read_me_first(context: PlatformMCPContext) -> dict[str, Any]:
    """Return the orientation guide for an agent on the platform server."""
    return {
        "server": "Unstract Platform MCP Server",
        "organization": context.org_name,
        "what_this_does": (
            "Unstract runs LLM-driven extraction over unstructured documents "
            "(PDFs, scans, images) and returns structured JSON. This server is "
            "scoped to a whole organization: it discovers what exists and can "
            "change the running state of those resources."
        ),
        "discovery_tools": [
            {"name": "whoami", "purpose": "See this credential's org, tier and budget."},
            {
                "name": "listApiDeployments",
                "purpose": "Find deployed extraction endpoints.",
            },
            {"name": "listWorkflows", "purpose": "Find the workflows behind them."},
            {"name": "listPipelines", "purpose": "Find ETL and task pipelines."},
            {
                "name": "listPromptStudioProjects",
                "purpose": "Find where extraction prompts are authored.",
            },
            {
                "name": "listPromptStudioDocuments",
                "purpose": (
                    "List a project's documents. The only source of the "
                    "document_id every billable tool below requires."
                ),
            },
            {
                "name": "listPrompts",
                "purpose": (
                    "List a project's prompts. The only source of the "
                    "prompt_id fetchResponse and bulkFetchResponse require."
                ),
            },
            {
                "name": "getWorkflowEndpoints",
                "purpose": "See how a workflow is wired (shape only, no config).",
            },
            {
                "name": "listToolInstances",
                "purpose": "See the tool steps inside a workflow.",
            },
            {"name": "listTags", "purpose": "List execution tags."},
        ],
        "observability_tools": [
            {
                "name": "listExecutions",
                "purpose": "Recent runs and their status. Start here to debug.",
            },
            {
                "name": "getExecutionDetail",
                "purpose": "Per-file results and errors for one run.",
            },
            {
                "name": "getUsageSummary",
                "purpose": "Tokens and cost recorded so far.",
            },
            {
                "name": "getExecutionStatus",
                "purpose": (
                    "Poll an extraction started by extractDocument. Free to "
                    "call, unlike the extraction itself."
                ),
            },
        ],
        "state_change_tools": [
            {
                "name": "setApiDeploymentActive",
                "purpose": "Take a deployment offline, or bring it back.",
            },
            {
                "name": "setPipelineActive",
                "purpose": "Pause or resume a pipeline's schedule.",
            },
        ],
        "billable_tools": [
            {
                "name": "executePipeline",
                "purpose": "Trigger a real pipeline run.",
            },
            {
                "name": "indexDocument",
                "purpose": "Embed a document so prompts can run against it.",
            },
            {
                "name": "fetchResponse",
                "purpose": "Run one prompt against an indexed document.",
            },
            {
                "name": "bulkFetchResponse",
                "purpose": "Run several prompts in one pass. Prefer over looping.",
            },
            {
                "name": "singlePassExtraction",
                "purpose": "Run a project's whole prompt set. Most expensive.",
            },
            {
                "name": "extractDocument",
                "purpose": (
                    "Run a deployment's extraction workflow over documents. "
                    "Needs an api_name from listApiDeployments."
                ),
            },
        ],
        "before_writing": (
            "State-change tools take effect immediately for the whole "
            "organization — there is no staging or dry-run mode. Confirm the "
            "target with a discovery tool first."
        ),
        "before_spending": (
            "Billable tools cost real money each call: they drive LLM "
            "inference, embedding and vector-store writes. They are budgeted "
            "per organization — call whoami to see how much of that budget "
            "remains. Index a document once and then run prompts against it; "
            "prefer bulkFetchResponse over repeated fetchResponse calls; and "
            "never call a billable tool to 'test' whether something works."
        ),
        "not_available": (
            "Creating or rotating API keys, and deleting workflows, "
            "deployments or projects, are deliberately not exposed here."
        ),
        "to_run_an_extraction": (
            "Call listApiDeployments for an api_name, then extractDocument "
            "with that name and your document URLs. If the response is not "
            "already COMPLETED, poll getExecutionStatus with the returned "
            "execution_id.\n\n"
            "The same extraction is also available on a deployment-scoped "
            "server at /deployment/api/<org>/<api_name>/mcp, which takes that "
            "one deployment's own API key and can reach nothing else. Both "
            "run the identical workflow — pick this server for one credential "
            "across the organization, or that one for a narrower blast radius."
        ),
        "scope_warning": (
            "This credential is a service account, which reaches ALL resources "
            "in the organization regardless of the role it was created with. "
            "Do not treat these listings as one person's view, and remember "
            "the write tools have the same reach."
        ),
    }


def whoami(context: PlatformMCPContext) -> dict[str, Any]:
    """Describe the calling credential, so an agent can reason about scope."""
    from platform_api.models import ApiKeyPermission

    key = context.platform_key
    try:
        permission = ApiKeyPermission(key.permission)
        can_write = permission.allows("POST")
        can_delete = permission.allows("DELETE")
    except ValueError:
        can_write = can_delete = False

    budget = spend_guard.peek(context.org_name)

    return {
        "organization": context.org_name,
        "key_name": key.name,
        "permission_tier": key.permission,
        "is_service_account": bool(getattr(context.user, "is_service_account", False)),
        "can_use_write_tools": can_write,
        "can_use_destructive_tools": can_delete,
        "billable_budget": {
            "used": budget.used,
            "limit": budget.limit,
            "remaining": max(0, budget.limit - budget.used),
            "window_minutes": round(budget.window_seconds / 60),
            "note": (
                "Counts calls to billable tools, not tokens. Pace yourself "
                "against `remaining`; when it reaches zero, billable tools are "
                "refused until the window rolls over."
            ),
        },
        "visibility": (
            "All resources in the organization. Service-account credentials "
            "bypass per-user sharing filters, so this key can read AND modify "
            "any resource in the organization."
        ),
    }


def list_api_deployments(context: PlatformMCPContext) -> dict[str, Any]:
    """List the organization's API deployments."""
    queryset = APIDeployment.objects.for_user(context.user).order_by("display_name")
    total = queryset.count()
    rows = queryset[:LIST_LIMIT]

    return {
        "count": total,
        "api_deployments": [
            {
                "id": str(row.id),
                "display_name": row.display_name,
                # api_name is what an agent needs to open a deployment-scoped
                # MCP session, so it is surfaced rather than left to the UI.
                "api_name": row.api_name,
                "description": row.description or None,
                "is_active": row.is_active,
                "workflow_id": str(row.workflow_id),
            }
            for row in rows
        ],
        **_truncation_note(len(rows), total),
    }


def list_workflows(context: PlatformMCPContext) -> dict[str, Any]:
    """List the organization's workflows."""
    queryset = Workflow.objects.for_user(context.user).order_by("workflow_name")
    total = queryset.count()
    rows = queryset[:LIST_LIMIT]

    return {
        "count": total,
        "workflows": [
            {
                "id": str(row.id),
                "workflow_name": row.workflow_name,
                "description": row.description or None,
                "is_active": row.is_active,
            }
            for row in rows
        ],
        **_truncation_note(len(rows), total),
    }


def list_prompt_studio_projects(context: PlatformMCPContext) -> dict[str, Any]:
    """List the organization's Prompt Studio projects."""
    queryset = CustomTool.objects.for_user(context.user).order_by("tool_name")
    total = queryset.count()
    rows = queryset[:LIST_LIMIT]

    return {
        "count": total,
        "prompt_studio_projects": [
            {
                "id": str(row.tool_id),
                "tool_name": row.tool_name,
                "description": row.description or None,
            }
            for row in rows
        ],
        **_truncation_note(len(rows), total),
    }


def list_pipelines(context: PlatformMCPContext) -> dict[str, Any]:
    """List the organization's ETL and task pipelines."""
    queryset = Pipeline.objects.for_user(context.user).order_by("pipeline_name")
    total = queryset.count()
    rows = queryset[:LIST_LIMIT]

    return {
        "count": total,
        "pipelines": [
            {
                "id": str(row.id),
                "pipeline_name": row.pipeline_name,
                "pipeline_type": row.pipeline_type,
                "active": row.active,
                "last_run_status": row.last_run_status,
            }
            for row in rows
        ],
        **_truncation_note(len(rows), total),
    }


# ============================ write tools ============================
#
# Authorization for these is not decided here. Each is registered with a
# `required_method`, and the view checks it against the platform key's tier
# using ``ApiKeyPermission.allows`` — the same method-based semantics the auth
# middleware already enforces for REST. Destructive operations therefore fall
# out as full_access-only without a second, parallel permission scheme.


def set_api_deployment_active_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "api_name": {
                "type": "string",
                "description": (
                    "The api_name of the deployment, as returned by listApiDeployments."
                ),
            },
            "is_active": {
                "type": "boolean",
                "description": (
                    "True to activate the deployment so it accepts extraction "
                    "requests, False to take it offline."
                ),
            },
        },
        "required": ["api_name", "is_active"],
    }


def set_api_deployment_active(
    context: PlatformMCPContext, api_name: str, is_active: bool
) -> dict[str, Any]:
    """Activate or deactivate an API deployment.

    Reversible by construction — the inverse call restores the previous state —
    which is why this is the write operation exposed rather than anything that
    destroys configuration.
    """
    deployment = (
        APIDeployment.objects.for_user(context.user).filter(api_name=api_name).first()
    )
    if deployment is None:
        raise MCPToolError(
            f"No API deployment named '{api_name}' in organization "
            f"'{context.org_name}'. Call listApiDeployments to see valid names."
        )

    was_active = deployment.is_active
    if was_active == is_active:
        return {
            "api_name": api_name,
            "is_active": is_active,
            "changed": False,
            "message": f"Deployment '{api_name}' was already "
            f"{'active' if is_active else 'inactive'}.",
        }

    deployment.is_active = is_active
    deployment.save(update_fields=["is_active"])
    logger.info(
        f"Platform MCP set deployment '{api_name}' active={is_active} "
        f"(org '{context.org_name}', key '{context.platform_key.name}')"
    )

    return {
        "api_name": api_name,
        "is_active": is_active,
        "changed": True,
        "previous_state": was_active,
    }


def execute_pipeline_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pipeline_id": {
                "type": "string",
                "description": (
                    "UUID of the pipeline to run, as returned by listPipelines."
                ),
            },
        },
        "required": ["pipeline_id"],
    }


def _resolve_pipeline(context: PlatformMCPContext, pipeline_id: str) -> Pipeline:
    """Find a pipeline the caller may reach, or refuse."""
    pipeline = Pipeline.objects.for_user(context.user).filter(id=pipeline_id).first()
    if pipeline is None:
        raise MCPToolError(
            f"No pipeline with id '{pipeline_id}' in organization "
            f"'{context.org_name}'. Call listPipelines to see valid ids."
        )
    return pipeline


def preflight_pipeline(
    context: PlatformMCPContext, pipeline_id: str, **_ignored: Any
) -> None:
    """Resolve the pipeline before any budget is claimed.

    ``execute_pipeline`` resolves it again inside the handler, but that runs
    after the budget is consumed and the budget is never refunded — so a stale
    id would cost a billable slot for a run that never started.
    """
    _resolve_pipeline(context, pipeline_id)


def execute_pipeline(context: PlatformMCPContext, pipeline_id: str) -> dict[str, Any]:
    """Trigger a run of an ETL or task pipeline.

    Delegates to ``PipelineManager``, which is what the REST endpoint calls, so
    scheduling, execution records and notifications behave identically to a run
    started from the UI.
    """
    from pipeline_v2.manager import PipelineManager

    pipeline = _resolve_pipeline(context, pipeline_id)

    if context.request is None:
        # The manager mutates request.data on the way to the workflow viewset,
        # so there is no meaningful fallback — fail loudly rather than
        # fabricate a request and produce a half-configured execution.
        raise MCPToolError(
            "Pipeline execution is unavailable in this context. "
            "Contact your Unstract administrator."
        )

    logger.info(
        f"Platform MCP executing pipeline '{pipeline_id}' "
        f"(org '{context.org_name}', key '{context.platform_key.name}')"
    )
    response = PipelineManager.execute_pipeline(
        request=context.request, pipeline_id=str(pipeline.id)
    )

    from mcp_server.tools.observability import redact_structure

    return {
        "pipeline_id": str(pipeline.id),
        "pipeline_name": pipeline.pipeline_name,
        "status": getattr(response, "status_code", None),
        # Raw manager response rather than named fields, so it gets the same
        # redaction net the error messages get.
        "result": redact_structure(getattr(response, "data", None)),
    }


def set_pipeline_active_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pipeline_id": {
                "type": "string",
                "description": ("UUID of the pipeline, as returned by listPipelines."),
            },
            "active": {
                "type": "boolean",
                "description": (
                    "True to enable the pipeline's schedule, False to pause it."
                ),
            },
        },
        "required": ["pipeline_id", "active"],
    }


def set_pipeline_active(
    context: PlatformMCPContext, pipeline_id: str, active: bool
) -> dict[str, Any]:
    """Enable or pause a pipeline's schedule."""
    pipeline = Pipeline.objects.for_user(context.user).filter(id=pipeline_id).first()
    if pipeline is None:
        raise MCPToolError(
            f"No pipeline with id '{pipeline_id}' in organization "
            f"'{context.org_name}'. Call listPipelines to see valid ids."
        )

    was_active = pipeline.active
    if was_active == active:
        return {
            "pipeline_id": str(pipeline.id),
            "active": active,
            "changed": False,
            "message": f"Pipeline was already {'active' if active else 'paused'}.",
        }

    pipeline.active = active
    pipeline.save(update_fields=["active"])
    logger.info(
        f"Platform MCP set pipeline '{pipeline_id}' active={active} "
        f"(org '{context.org_name}', key '{context.platform_key.name}')"
    )

    return {
        "pipeline_id": str(pipeline.id),
        "pipeline_name": pipeline.pipeline_name,
        "active": active,
        "changed": True,
        "previous_state": was_active,
    }
