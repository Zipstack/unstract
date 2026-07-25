"""Read-only tools for the organization-scoped MCP server.

Every listing goes through the model's own ``for_user`` manager rather than a
raw queryset, so the platform's sharing and visibility rules apply here exactly
as they do in the UI — this app does not get its own opinion about who may see
what.

One caveat those managers impose, which the tool descriptions state plainly:
a platform key resolves to a service account, and ``for_user`` short-circuits
to "everything in the organization" for service accounts. These tools therefore
see all org resources regardless of the role the key was created with.
"""

import logging
from typing import Any

from api_v2.models import APIDeployment
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from workflow_manager.workflow_v2.models.workflow import Workflow

from mcp_server.context import PlatformMCPContext

logger = logging.getLogger(__name__)

# Listings are bounded so a large organization cannot blow up an agent's
# context window. Chosen to comfortably cover real orgs while still being a
# ceiling; tools report when they hit it rather than truncating silently.
LIST_LIMIT = 100


def no_args_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


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
            "scoped to a whole organization and is READ-ONLY: it lets you "
            "discover what exists — deployments, workflows, Prompt Studio "
            "projects — but not change or run anything."
        ),
        "tools": [
            {"name": "whoami", "purpose": "See this credential's org, tier and scope."},
            {
                "name": "listApiDeployments",
                "purpose": "Find deployed extraction endpoints.",
            },
            {"name": "listWorkflows", "purpose": "Find the pipelines behind them."},
            {
                "name": "listPromptStudioProjects",
                "purpose": "Find where extraction prompts are authored.",
            },
        ],
        "to_run_an_extraction": (
            "This server cannot extract. Call listApiDeployments to get an "
            "api_name, then open a separate MCP session against that "
            "deployment's own endpoint — /mcp/<org>/<api_name>/ — using that "
            "deployment's API key. That session exposes extractDocument."
        ),
        "scope_warning": (
            "This credential is a service account, which sees ALL resources in "
            "the organization regardless of the role it was created with. Do "
            "not treat these listings as one person's view."
        ),
    }


def whoami(context: PlatformMCPContext) -> dict[str, Any]:
    """Describe the calling credential, so an agent can reason about scope."""
    key = context.platform_key
    return {
        "organization": context.org_name,
        "key_name": key.name,
        "permission_tier": key.permission,
        "is_service_account": bool(getattr(context.user, "is_service_account", False)),
        "access": "read-only (this MCP server exposes no write tools)",
        "visibility": (
            "All resources in the organization. Service-account credentials "
            "bypass per-user sharing filters."
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
