"""Read-only tools describing the connected API deployment."""

import logging
from typing import Any

from mcp_v2.context import MCPContext

logger = logging.getLogger(__name__)


def read_me_first(context: MCPContext) -> dict[str, Any]:
    """Return the orientation guide for a coding agent.

    Deliberately built from the live deployment rather than a static string —
    the agent should learn the name of the deployment it is actually talking
    to, not a generic description of Unstract.
    """
    return {
        "server": "Unstract MCP Server",
        "connected_deployment": {
            "name": context.api.display_name,
            "description": context.api.description or None,
            "is_active": context.api.is_active,
        },
        "what_this_does": (
            "Unstract runs LLM-driven extraction over unstructured documents "
            "(PDFs, scans, images) and returns structured JSON. This MCP "
            "server is scoped to a single API deployment, which encapsulates "
            "one extraction workflow — the prompts and output schema are fixed "
            "by that deployment, so you supply documents, not instructions."
        ),
        "tools": [
            {
                "name": "getApiInfo",
                "purpose": "Learn what the connected deployment extracts.",
            },
            {
                "name": "extractDocument",
                "purpose": "Run extraction over document URLs. Consumes quota.",
            },
            {
                "name": "getExecutionStatus",
                "purpose": "Poll for the result of a pending extraction.",
            },
        ],
        "recommended_workflow": [
            "1. Call getApiInfo to confirm the deployment is active and see "
            "what it is meant to process.",
            "2. Call extractDocument with the URL(s) of the document(s).",
            "3. If the response has execution_status COMPLETED, the result is "
            "already in the response — you are done.",
            "4. Otherwise poll getExecutionStatus with the returned "
            "execution_id until the status is COMPLETED or ERROR, pausing a "
            "few seconds between polls.",
        ],
        "notes": [
            "Documents are fetched server-side from the URLs you provide, and "
            "only S3 pre-signed URLs are accepted — an ordinary public link "
            "is rejected. Upload to S3 and pre-sign it first if needed.",
            "extractDocument consumes the organization's extraction quota. "
            "Never call it speculatively, and never retry a call that already "
            "returned an execution_id — poll instead.",
        ],
    }


def get_api_info_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "required": []}


def get_api_info(context: MCPContext) -> dict[str, Any]:
    """Return metadata about the connected API deployment."""
    api = context.api
    return {
        "id": str(api.id),
        "display_name": api.display_name,
        "api_name": api.api_name,
        "description": api.description or None,
        "is_active": api.is_active,
        "workflow": {
            "id": str(api.workflow_id),
            "name": api.workflow.workflow_name,
        },
    }
