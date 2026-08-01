"""Billable Prompt Studio tools for the organization-scoped MCP server.

These drive real LLM inference, embedding and vector-store writes, so each is
registered ``billable=True`` and budgeted by ``mcp_server.spend_guard``.

Every tool here delegates to ``PromptStudioCoreView`` rather than
reimplementing its logic. Those actions carry a great deal that is easy to get
subtly wrong — run-id generation, profile resolution, lookup gating, indexing
race avoidance, Celery dispatch — and a parallel implementation would drift
from the UI's behaviour on the first change to either. Dispatching the real
view keeps one code path, and keeps its permission and sharing checks.
"""

import logging
from typing import Any

from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

from mcp_server.context import PlatformMCPContext
from mcp_server.exceptions import MCPToolError

logger = logging.getLogger(__name__)


def _resolve_project(context: PlatformMCPContext, project_id: str) -> CustomTool:
    """Find a Prompt Studio project the caller may reach, or refuse.

    Resolving through ``for_user`` is what keeps a key inside its own
    organization — the view's own ``get_object`` would apply the same rules,
    but failing here produces a message the agent can act on rather than a
    404 surfaced as an unexpected error.
    """
    project = CustomTool.objects.for_user(context.user).filter(tool_id=project_id).first()
    if project is None:
        raise MCPToolError(
            f"No Prompt Studio project with id '{project_id}' in organization "
            f"'{context.org_name}'. Call listPromptStudioProjects for valid ids."
        )
    return project


def _dispatch(context: PlatformMCPContext, action: str, project_id: str, payload: dict):
    """Invoke a PromptStudioCoreView action with the MCP request.

    The underlying view reads its arguments from ``request.data`` and resolves
    the organization from the request, both of which the platform MCP request
    already carries — the middleware set the org, and this server's context
    holds the real DRF request.
    """
    if context.request is None:
        raise MCPToolError(
            "Prompt Studio operations are unavailable in this context. "
            "Contact your Unstract administrator."
        )

    request = context.request
    # The view reads its inputs from request.data. Replacing it wholesale keeps
    # the JSON-RPC envelope (which carries the MCP method, not the tool's
    # arguments) from reaching the view.
    original_data = request.data
    try:
        request._full_data = payload
        # Do NOT route through as_view(): it calls initialize_request(), which
        # builds a *new* DRF Request with no _full_data, so .data re-parses
        # request.body — the JSON-RPC envelope — and the action never sees
        # document_id/prompt_id. Call the action on a bare instance holding this
        # request instead, the same pattern PipelineManager.execute_pipeline
        # uses for executePipeline.
        view_instance = PromptStudioCoreView()
        view_instance.request = request
        view_instance.args = ()
        view_instance.kwargs = {"pk": project_id}
        # get_object()/get_serializer() read self.request and self.kwargs["pk"];
        # format_kwarg is what DRF's content negotiation path expects to exist.
        view_instance.format_kwarg = None
        response = getattr(view_instance, action)(request, pk=project_id)
    finally:
        request._full_data = original_data

    return response


def _result(response, project: CustomTool) -> dict[str, Any]:
    """Normalise a DRF response into a tool result.

    A non-2xx status is returned as data rather than raised: the view's own
    error bodies (a missing prompt id, an unindexed document) are precisely
    what the agent needs to correct its next call.
    """
    from mcp_server.tools.observability import redact_structure

    status_code = getattr(response, "status_code", None)
    data = getattr(response, "data", None)
    ok = status_code is not None and 200 <= status_code < 300

    result: dict[str, Any] = {
        "project_id": str(project.tool_id),
        "project_name": project.tool_name,
        "ok": ok,
        "status": status_code,
        # This app did not assemble `data` field by field — it is whatever the
        # delegated view returned, error bodies included — so it gets the same
        # redaction net the named error messages get.
        "result": redact_structure(data),
    }
    if not ok:
        result["note"] = (
            "The operation was rejected. Read `result` for the reason — it is "
            "usually a missing or invalid argument, or a document that has not "
            "been indexed yet."
        )
    return result


def index_document_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": (
                    "UUID of the Prompt Studio project, from listPromptStudioProjects."
                ),
            },
            "document_id": {
                "type": "string",
                "description": "UUID of the document within that project to index.",
            },
        },
        "required": ["project_id", "document_id"],
    }


def index_document(
    context: PlatformMCPContext, project_id: str, document_id: str
) -> dict[str, Any]:
    """Index a document so prompts can be run against it."""
    project = _resolve_project(context, project_id)
    logger.info(
        f"MCP index_document project='{project_id}' document='{document_id}' "
        f"(org '{context.org_name}', key '{context.platform_key.name}')"
    )
    response = _dispatch(
        context, "index_document", project_id, {"document_id": document_id}
    )
    return _result(response, project)


def fetch_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "UUID of the Prompt Studio project.",
            },
            "document_id": {
                "type": "string",
                "description": "UUID of the document to run the prompt against.",
            },
            "prompt_id": {
                "type": "string",
                "description": "UUID of the prompt to run.",
            },
            "profile_manager_id": {
                "type": "string",
                "description": (
                    "Optional UUID of an LLM profile to override the project's default."
                ),
            },
        },
        "required": ["project_id", "document_id", "prompt_id"],
    }


def fetch_response(
    context: PlatformMCPContext,
    project_id: str,
    document_id: str,
    prompt_id: str,
    profile_manager_id: str | None = None,
) -> dict[str, Any]:
    """Run a single prompt against an indexed document."""
    project = _resolve_project(context, project_id)
    payload: dict[str, Any] = {"document_id": document_id, "id": prompt_id}
    if profile_manager_id:
        payload["profile_manager"] = profile_manager_id

    logger.info(
        f"MCP fetch_response project='{project_id}' prompt='{prompt_id}' "
        f"(org '{context.org_name}', key '{context.platform_key.name}')"
    )
    response = _dispatch(context, "fetch_response", project_id, payload)
    return _result(response, project)


def bulk_fetch_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "UUID of the Prompt Studio project.",
            },
            "document_id": {
                "type": "string",
                "description": "UUID of the document to run the prompts against.",
            },
            "prompt_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "description": "UUIDs of the prompts to run.",
            },
        },
        "required": ["project_id", "document_id", "prompt_ids"],
    }


def bulk_fetch_response(
    context: PlatformMCPContext,
    project_id: str,
    document_id: str,
    prompt_ids: list[str],
) -> dict[str, Any]:
    """Run several prompts against one document in a single pass.

    Preferred over repeated ``fetchResponse`` calls: it indexes once and
    dispatches one task, which is both cheaper and avoids the
    document-being-indexed race that concurrent single calls provoke.
    """
    project = _resolve_project(context, project_id)
    logger.info(
        f"MCP bulk_fetch_response project='{project_id}' "
        f"prompts={len(prompt_ids)} (org '{context.org_name}', "
        f"key '{context.platform_key.name}')"
    )
    response = _dispatch(
        context,
        "bulk_fetch_response",
        project_id,
        {"document_id": document_id, "prompt_ids": prompt_ids},
    )
    return _result(response, project)


def single_pass_extraction_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "UUID of the Prompt Studio project.",
            },
            "document_id": {
                "type": "string",
                "description": "UUID of the document to extract from.",
            },
        },
        "required": ["project_id", "document_id"],
    }


def single_pass_extraction(
    context: PlatformMCPContext, project_id: str, document_id: str
) -> dict[str, Any]:
    """Run the project's whole prompt set in a single LLM pass."""
    project = _resolve_project(context, project_id)
    logger.info(
        f"MCP single_pass_extraction project='{project_id}' "
        f"document='{document_id}' (org '{context.org_name}', "
        f"key '{context.platform_key.name}')"
    )
    response = _dispatch(
        context, "single_pass_extraction", project_id, {"document_id": document_id}
    )
    return _result(response, project)


def list_prompt_studio_documents_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": (
                    "UUID of the Prompt Studio project, from listPromptStudioProjects."
                ),
            },
        },
        "required": ["project_id"],
    }


def list_prompt_studio_documents(
    context: PlatformMCPContext, project_id: str
) -> dict[str, Any]:
    """List the documents already uploaded to a Prompt Studio project.

    This is the only producer of the ``document_id`` that every billable tool
    in this module requires, so without it those tools are unreachable.

    Documents are resolved *through* the project rather than by a direct
    ``DocumentManager`` lookup. The platform key authenticates as a service
    account, for which ``for_user`` returns everything, so the project join in
    ``_resolve_project`` is the scoping that actually holds.
    """
    project = _resolve_project(context, project_id)
    documents = project.document_managers.all().order_by("document_name")

    return {
        "project_id": str(project.tool_id),
        "project_name": project.tool_name,
        "documents": [
            {
                "document_id": str(document.document_id),
                "document_name": document.document_name,
            }
            for document in documents
        ],
    }


def list_prompts_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": (
                    "UUID of the Prompt Studio project, from listPromptStudioProjects."
                ),
            },
        },
        "required": ["project_id"],
    }


def list_prompts(context: PlatformMCPContext, project_id: str) -> dict[str, Any]:
    """List a project's prompts, which is where ``prompt_id`` comes from.

    The response is built field by field rather than through a serializer.
    ``ToolStudioPrompt`` carries a ``profile_manager`` FK — the LLM, embedding
    and vector-store adapters backing the prompt — and a
    ``postprocessing_webhook_url``. A serializer would carry both out to the
    agent, which is exactly what this server's README promises it does not do.
    Adding a field here is therefore a deliberate act.
    """
    project = _resolve_project(context, project_id)
    prompts = project.mapped_prompt.all().order_by("sequence_number")

    return {
        "project_id": str(project.tool_id),
        "project_name": project.tool_name,
        "prompts": [
            {
                "prompt_id": str(prompt.prompt_id),
                "prompt_key": prompt.prompt_key,
                "prompt": prompt.prompt,
                "prompt_type": prompt.prompt_type,
                "enforce_type": prompt.enforce_type,
                "sequence_number": prompt.sequence_number,
                "active": prompt.active,
            }
            for prompt in prompts
        ],
    }


def preflight_project(
    context: PlatformMCPContext, project_id: str, **_ignored: Any
) -> None:
    """Resolve the project before any budget is claimed.

    Every billable tool in this module already calls ``_resolve_project`` — but
    inside the handler, which runs *after* the budget is consumed. A stale or
    mistyped ``project_id`` would therefore cost a slot for a call that never
    reached an LLM. Running the same resolution first makes that refusal free.

    Cheap and deterministic by design: a single indexed lookup the handler
    repeats anyway, not work that could itself fail transiently.
    """
    _resolve_project(context, project_id)
