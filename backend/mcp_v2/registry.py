"""Tool registry for the hosted MCP server.

Tools are plain callables registered with the JSON schema MCP clients need in
order to call them. Each tool receives the resolved deployment context as its
first argument, so tool implementations never re-do auth or org resolution.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPTool:
    """A single tool exposed over the MCP transport.

    Attributes:
        name: Tool name as seen by the MCP client.
        description: Prompt-facing description. Written for an LLM audience —
            it is the only guidance the calling agent gets.
        input_schema: JSON schema for the tool's arguments.
        handler: Callable invoked as ``handler(context, **arguments)``.
        writes: True when the tool has side effects (consumes quota, starts an
            execution). Read-only tools are safe to retry; write tools are not.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    writes: bool = False

    def to_mcp_schema(self) -> dict[str, Any]:
        """Serialize to the shape returned by `tools/list`."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPToolRegistry:
    """Ordered name -> tool mapping.

    Ordering is preserved so `tools/list` presents tools in the order they were
    registered; agents weight earlier tools more heavily, and `readMeFirst`
    needs to come first.
    """

    _tools: dict[str, MCPTool] = field(default_factory=dict)

    def register(self, tool: MCPTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate MCP tool registration: '{tool.name}'")
        self._tools[tool.name] = tool

    def get(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def list_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_mcp_schema() for tool in self._tools.values()]


def build_registry() -> MCPToolRegistry:
    """Build the registry of tools exposed by the Unstract MCP server.

    Imported lazily inside the function so that registering a tool cannot
    trigger Django model imports at module-import time.
    """
    from mcp_v2.tools.execution import (
        extract_document,
        extract_document_schema,
        get_execution_status,
        get_execution_status_schema,
    )
    from mcp_v2.tools.info import get_api_info, get_api_info_schema, read_me_first

    registry = MCPToolRegistry()

    registry.register(
        MCPTool(
            name="readMeFirst",
            description=(
                "START HERE. Returns a guide to this MCP server: what the "
                "connected Unstract API deployment does, the available tools, "
                "and the recommended call sequence. Takes no arguments."
            ),
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=read_me_first,
        )
    )
    registry.register(
        MCPTool(
            name="getApiInfo",
            description=(
                "Get details of the Unstract API deployment this MCP server is "
                "connected to: its display name, description, the workflow it "
                "runs, and whether it is active. Call this to learn what kind of "
                "document the deployment expects before extracting. "
                "Takes no arguments."
            ),
            input_schema=get_api_info_schema(),
            handler=get_api_info,
        )
    )
    registry.register(
        MCPTool(
            name="extractDocument",
            description=(
                "Run the connected Unstract API deployment over one or more "
                "documents and return the structured extraction result.\n\n"
                "Documents are supplied as S3 pre-signed URLs, which Unstract "
                "fetches server-side — ordinary public links are rejected, so "
                "upload to S3 and pre-sign first if the document is not "
                "already there. Extraction is asynchronous: when it does not "
                "finish within `timeout` seconds this returns "
                "`execution_status: PENDING` along with an `execution_id`. Poll "
                "`getExecutionStatus` with that id to collect the result.\n\n"
                "This consumes the organization's extraction quota — do not call "
                "it speculatively or retry a call that already returned an "
                "execution_id."
            ),
            input_schema=extract_document_schema(),
            handler=extract_document,
            writes=True,
        )
    )
    registry.register(
        MCPTool(
            name="getExecutionStatus",
            description=(
                "Fetch the status and, once available, the result of an "
                "extraction previously started by `extractDocument`. Pass the "
                "`execution_id` that call returned.\n\n"
                "Returns an `execution_status` of PENDING, EXECUTING, COMPLETED "
                "or ERROR. Poll while it is PENDING or EXECUTING, leaving a few "
                "seconds between calls."
            ),
            input_schema=get_execution_status_schema(),
            handler=get_execution_status,
        )
    )

    return registry


# Single shared registry. The tool set is static, so building it once at import
# time is safe and keeps per-request work down.
TOOL_REGISTRY = build_registry()
