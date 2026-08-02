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
        title: Human-readable name a host shows in its UI, where the camelCase
            tool name reads poorly. Defaults to the tool name when unset.
        writes: True when the tool has side effects (consumes quota, starts an
            execution). Read-only tools are safe to retry; write tools are not.
        required_method: The HTTP method this tool's REST equivalent would use.
            Platform API key tiers are defined in terms of HTTP methods
            (``ApiKeyPermission.allows``), and every JSON-RPC message arrives
            as an HTTP POST regardless of the tool it carries — so
            declaring the *equivalent* method is what lets the existing tier
            semantics apply per tool instead of per request. "GET" for reads,
            "POST" for mutations, "DELETE" for destructive operations (which
            only ``full_access`` permits). Unused by the deployment server,
            whose key has no tiers.
        billable: True when invoking the tool costs money — LLM inference,
            embedding, indexing, or a pipeline run. Budgeted per organization
            by ``mcp_server.spend_guard``. Deliberately distinct from
            ``writes``: a tool can mutate cheaply (pausing a schedule) or cost
            money without changing configuration (running an extraction).
        idempotent: True when repeating the call with the same arguments lands
            in the same state — activating an already-active deployment, or
            pausing an already-paused schedule. False when each call creates
            new work, such as starting an execution. Only meaningful for tools
            that write; a read tool is idempotent by definition.

            Declared rather than derived from ``billable``: the deployment
            server's ``extractDocument`` is not billable there (its cost is
            bounded by the rate limiter rather than the spend guard) but still
            starts a fresh execution on every call, so deriving would have
            advertised it as safe to repeat.
        preflight: Optional ``preflight(context, **arguments)`` run *before* the
            billable budget is claimed. It exists because the budget is
            consumed on invocation and never refunded, so a call refused for a
            reason the caller could have been told about up front — a
            deployment name that does not resolve — would otherwise burn a slot
            having spent nothing. Raise ``MCPToolError`` to refuse.

            Only for checks that are cheap and certain: resolving a named
            resource, not anything that could itself fail transiently. A tool
            whose arguments are all opaque ids the caller got from a listing
            does not need one.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    title: str = ""
    writes: bool = False
    required_method: str = "GET"
    billable: bool = False
    idempotent: bool = False
    preflight: Callable[..., Any] | None = None

    def annotations(self) -> dict[str, Any]:
        """Behaviour hints for `tools/list`, built from the flags above.

        ``readOnlyHint`` and ``destructiveHint`` are *derived* from
        ``writes``/``billable``/``required_method`` rather than declared per
        tool, so a tool cannot advertise something its own flags contradict —
        the same reason ``required_method`` is enforced at registration instead
        of being trusted. ``idempotentHint`` is the exception and is declared;
        see the ``idempotent`` field for why no flag here implies it.

        Spec defaults matter here and are not what you would guess
        (`ToolAnnotations`, rev 2025-06-18):

        * ``readOnlyHint`` defaults to **false**, so a read tool that stays
          silent looks like a mutator. Every read tool must say so explicitly.
        * ``destructiveHint`` defaults to **true**, so a write tool that stays
          silent looks destructive. Every write tool here is reversible —
          activating a deployment, pausing a schedule, starting an execution —
          and none deletes anything, which is a deliberate property of this
          surface, so it is stated rather than left to the default.
        * ``destructiveHint`` and ``idempotentHint`` are meaningful only when
          ``readOnlyHint`` is false, so they are omitted for read tools rather
          than set to a value a client is told to ignore.

        These are hints, not enforcement: the spec tells clients to distrust
        annotations from untrusted servers, and the real gate stays
        ``check_tool_allowed`` plus the spend guard.
        """
        read_only = not self.writes and not self.billable
        hints: dict[str, Any] = {
            "title": self.title or self.name,
            "readOnlyHint": read_only,
            # Every tool here reaches Unstract's own APIs and, for the
            # extraction paths, the documents and model providers behind them.
            # That is an open world by the spec's definition.
            "openWorldHint": True,
        }
        if not read_only:
            # DELETE is the tier reserved for destructive operations; nothing
            # on this surface declares it today, and the registry refuses a
            # write tool that leaves required_method at the "GET" default.
            hints["destructiveHint"] = self.required_method == "DELETE"
            hints["idempotentHint"] = self.idempotent
        return hints

    def to_mcp_schema(self) -> dict[str, Any]:
        """Serialize to the shape returned by `tools/list`."""
        return {
            "name": self.name,
            "title": self.title or self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": self.annotations(),
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
        if tool.writes and tool.required_method == "GET":
            # `writes` and `required_method` are independent fields, so
            # MCPTool(..., writes=True) silently keeps the "GET" default — and
            # ApiKeyPermission.allows("GET") is true for *every* tier, so
            # check_tool_allowed would wave the tool through for a read-only
            # key. The unsafe pairing being the default is the wrong way round
            # for the invariant the whole tier model rests on.
            #
            # Enforced at registration rather than only in a test: a tool
            # declared wrongly cannot reach a running server, whereas a CI
            # assertion can be deselected or simply not run on the branch that
            # adds the tool.
            raise ValueError(
                f"MCP tool '{tool.name}' declares writes=True with "
                "required_method='GET'. Every key tier allows GET, so the tier "
                "guard would let a read-only key invoke it. Declare the method "
                "the tool's REST equivalent would use — 'POST' for a mutation, "
                "'DELETE' for a destructive operation."
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> MCPTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def list_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_mcp_schema() for tool in self._tools.values()]


def build_deployment_registry() -> MCPToolRegistry:
    """Build the tools exposed by the deployment-scoped MCP server.

    Imported lazily inside the function so that registering a tool cannot
    trigger Django model imports at module-import time.
    """
    from mcp_server.tools.execution import (
        extract_document,
        extract_document_schema,
        get_execution_status,
        get_execution_status_schema,
    )
    from mcp_server.tools.info import get_api_info, get_api_info_schema, read_me_first

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
            # The deployment server has no tiers, so nothing reads this here —
            # but declaring it truthfully lets the write/method invariant in
            # `register` be unconditional rather than opt-in.
            required_method="POST",
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


def build_platform_registry() -> MCPToolRegistry:
    """Build the tools exposed by the organization-scoped MCP server.

    Each tool declares the HTTP method its REST equivalent would use, which is
    how the platform key's existing permission tier applies per tool rather
    than per request — see ``MCPTool.required_method``.

    Two categories are deliberately absent:

    * **Credential operations.** Creating or rotating an API key returns the
      secret in its response, so an MCP tool for it would be an exfiltration
      path for an agent processing untrusted document content. The codebase
      already reasons this way — see ``CanRotatePlatformApiKey``'s docstring on
      why rotation is ``full_access``-only.
    * **Deletions.** Removing a workflow, deployment or Prompt Studio project
      destroys work that no inverse call restores. The write tools here are
      reversible by construction.
    """
    from mcp_server.tools.observability import (
        get_execution_detail,
        get_execution_detail_schema,
        get_usage_summary,
        get_usage_summary_schema,
        get_workflow_endpoints,
        get_workflow_endpoints_schema,
        list_executions,
        list_executions_schema,
        list_tags,
        list_tool_instances,
        list_tool_instances_schema,
    )
    from mcp_server.tools.platform import (
        _ORG_WIDE_WARNING,
        execute_pipeline,
        execute_pipeline_schema,
        list_api_deployments,
        list_pipelines,
        list_prompt_studio_projects,
        list_workflows,
        no_args_schema,
        platform_read_me_first,
        preflight_pipeline,
        set_api_deployment_active,
        set_api_deployment_active_schema,
        set_pipeline_active,
        set_pipeline_active_schema,
        whoami,
    )
    from mcp_server.tools.platform_execution import (
        get_platform_execution_status,
        platform_execution_status_schema,
        platform_extract_document,
        platform_extract_document_schema,
        preflight_extract_document,
    )
    from mcp_server.tools.prompt_studio import (
        bulk_fetch_response,
        bulk_fetch_response_schema,
        fetch_response,
        fetch_response_schema,
        index_document,
        index_document_schema,
        list_prompt_studio_documents,
        list_prompt_studio_documents_schema,
        list_prompts,
        list_prompts_schema,
        preflight_project,
        single_pass_extraction,
        single_pass_extraction_schema,
    )

    registry = MCPToolRegistry()

    registry.register(
        MCPTool(
            name="readMeFirst",
            description=(
                "START HERE. Returns a guide to this MCP server: what it can "
                "see in the connected Unstract organization, the available "
                "tools, and the recommended call sequence. Takes no arguments."
            ),
            input_schema=no_args_schema(),
            handler=platform_read_me_first,
        )
    )
    registry.register(
        MCPTool(
            name="whoami",
            description=(
                "Describe the credential this session is using: the "
                "organization it belongs to, its permission tier, and the "
                "scope of what it can see. Call this when a tool returns less "
                "or more than you expected. Takes no arguments."
            ),
            input_schema=no_args_schema(),
            handler=whoami,
        )
    )
    registry.register(
        MCPTool(
            name="listApiDeployments",
            description=(
                "List the organization's API deployments — the deployed "
                "extraction endpoints. Use this to discover what can be "
                "extracted and to find the api_name needed to connect a "
                "deployment-scoped MCP session. Takes no arguments."
            ),
            input_schema=no_args_schema(),
            handler=list_api_deployments,
        )
    )
    registry.register(
        MCPTool(
            name="listWorkflows",
            description=(
                "List the organization's workflows — the pipelines that API "
                "deployments and ETL pipelines run. Takes no arguments."
            ),
            input_schema=no_args_schema(),
            handler=list_workflows,
        )
    )
    registry.register(
        MCPTool(
            name="listPromptStudioProjects",
            description=(
                "List the organization's Prompt Studio projects, where "
                "extraction prompts are authored before being exported as "
                "tools and deployed. Takes no arguments."
            ),
            input_schema=no_args_schema(),
            handler=list_prompt_studio_projects,
        )
    )
    # Registered next to the project listing rather than beside the billable
    # tools they feed: an agent reads this list top-down, and the id-producing
    # step belongs immediately after the project it drills into.
    registry.register(
        MCPTool(
            name="listPromptStudioDocuments",
            description=(
                "List the documents uploaded to a Prompt Studio project.\n\n"
                "Call this to obtain the `document_id` that indexDocument, "
                "fetchResponse, bulkFetchResponse and singlePassExtraction "
                "require. Free to call — it reads metadata only and runs no "
                "inference."
            ),
            input_schema=list_prompt_studio_documents_schema(),
            handler=list_prompt_studio_documents,
        )
    )
    registry.register(
        MCPTool(
            name="listPrompts",
            description=(
                "List a Prompt Studio project's prompts: their keys, text, "
                "type and order.\n\n"
                "Call this to obtain the `prompt_id` that fetchResponse and "
                "bulkFetchResponse require, or to see what a project extracts "
                "before spending money running it. Free to call."
            ),
            input_schema=list_prompts_schema(),
            handler=list_prompts,
        )
    )
    registry.register(
        MCPTool(
            name="listPipelines",
            description=(
                "List the organization's ETL and task pipelines, with their "
                "schedule state and the status of their last run. Takes no "
                "arguments."
            ),
            input_schema=no_args_schema(),
            handler=list_pipelines,
        )
    )

    registry.register(
        MCPTool(
            name="setApiDeploymentActive",
            description=(
                "Activate or deactivate an API deployment. A deactivated "
                "deployment rejects extraction requests; activating it again "
                "restores service.\n\n"
                "Use this to take a misbehaving deployment offline, or to "
                "bring one back. The change is immediate and affects every "
                "caller of that deployment, not just this session.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=set_api_deployment_active_schema(),
            handler=set_api_deployment_active,
            title="Activate or Deactivate API Deployment",
            writes=True,
            required_method="POST",
            # Setting active=True on an already-active deployment lands in the
            # same state; nothing new is created.
            idempotent=True,
        )
    )
    registry.register(
        MCPTool(
            name="setPipelineActive",
            description=(
                "Enable or pause a pipeline's schedule. A paused pipeline "
                "stops running on its schedule but is not deleted, and "
                "enabling it resumes the existing schedule.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=set_pipeline_active_schema(),
            handler=set_pipeline_active,
            title="Enable or Pause Pipeline Schedule",
            writes=True,
            required_method="POST",
            # Pausing an already-paused schedule is a no-op, as is enabling an
            # enabled one.
            idempotent=True,
        )
    )
    registry.register(
        MCPTool(
            name="executePipeline",
            description=(
                "Trigger an immediate run of an ETL or task pipeline, "
                "independently of its schedule.\n\n"
                "This does real work: it processes whatever documents the "
                "pipeline's source currently holds and writes to its "
                "destination, consuming the organization's quota. It is not a "
                "dry run and cannot be undone — do not call it to 'test' a "
                "pipeline.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=execute_pipeline_schema(),
            handler=execute_pipeline,
            writes=True,
            required_method="POST",
            billable=True,
            preflight=preflight_pipeline,
        )
    )

    # ---- observability: what happened, and what it cost ----

    registry.register(
        MCPTool(
            name="listExecutions",
            description=(
                "List recent workflow executions, newest first, with per-run "
                "status and file counts.\n\n"
                "This is the tool for 'did that run?' and 'why did it fail?'. "
                "Optionally filter by workflow_id or status."
            ),
            input_schema=list_executions_schema(),
            handler=list_executions,
        )
    )
    registry.register(
        MCPTool(
            name="getExecutionDetail",
            description=(
                "Get per-file detail for one execution — which files "
                "succeeded, which failed, and the error for each. Use after "
                "listExecutions has identified a run worth investigating."
            ),
            input_schema=get_execution_detail_schema(),
            handler=get_execution_detail,
        )
    )
    registry.register(
        MCPTool(
            name="getUsageSummary",
            description=(
                "Aggregate token and cost usage recorded for this "
                "organization. Historical accounting of what has already been "
                "spent — not a budget or a limit. Takes no arguments."
            ),
            input_schema=get_usage_summary_schema(),
            handler=get_usage_summary,
        )
    )
    registry.register(
        MCPTool(
            name="getWorkflowEndpoints",
            description=(
                "Describe how a workflow is wired: its source and destination "
                "endpoint types, and the name of the connector each uses.\n\n"
                "Connector credentials and endpoint configuration are "
                "deliberately not returned — only the shape of the connection."
            ),
            input_schema=get_workflow_endpoints_schema(),
            handler=get_workflow_endpoints,
        )
    )
    registry.register(
        MCPTool(
            name="listToolInstances",
            description=(
                "List the tool steps configured inside a workflow, in "
                "execution order. Use this to understand what a workflow "
                "actually does before running it."
            ),
            input_schema=list_tool_instances_schema(),
            handler=list_tool_instances,
        )
    )
    registry.register(
        MCPTool(
            name="listTags",
            description=(
                "List the organization's tags, which label workflow "
                "executions for grouping and filtering. Takes no arguments."
            ),
            input_schema=no_args_schema(),
            handler=list_tags,
        )
    )

    # ---- billable Prompt Studio operations ----
    #
    # Each drives real LLM inference or embedding work, so each is billable and
    # budgeted per organization by mcp_server.spend_guard.

    registry.register(
        MCPTool(
            name="indexDocument",
            description=(
                "Index a document in a Prompt Studio project so prompts can be "
                "run against it.\n\n"
                "**Costs money**: this embeds the document and writes to the "
                "vector store. Index once, then run as many prompts as you "
                "need against it — do not re-index between prompts.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=index_document_schema(),
            handler=index_document,
            writes=True,
            required_method="POST",
            billable=True,
            preflight=preflight_project,
        )
    )
    registry.register(
        MCPTool(
            name="fetchResponse",
            description=(
                "Run one Prompt Studio prompt against an indexed document and "
                "return the extracted response.\n\n"
                "**Costs money**: this is a live LLM call. If you need several "
                "prompts against the same document, use bulkFetchResponse "
                "instead — it is cheaper and avoids an indexing race.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=fetch_response_schema(),
            handler=fetch_response,
            writes=True,
            required_method="POST",
            billable=True,
            preflight=preflight_project,
        )
    )
    registry.register(
        MCPTool(
            name="bulkFetchResponse",
            description=(
                "Run several Prompt Studio prompts against one document in a "
                "single pass.\n\n"
                "**Costs money.** Prefer this over repeated fetchResponse "
                "calls: it indexes once and dispatches one task, which is both "
                "cheaper and avoids the 'document being indexed' race that "
                "concurrent single calls provoke.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=bulk_fetch_response_schema(),
            handler=bulk_fetch_response,
            writes=True,
            required_method="POST",
            billable=True,
            preflight=preflight_project,
        )
    )
    registry.register(
        MCPTool(
            name="singlePassExtraction",
            description=(
                "Run a Prompt Studio project's entire prompt set against a "
                "document in one LLM pass.\n\n"
                "**Costs money**, and is the most expensive tool here. Use it "
                "when you want the project's full output; use fetchResponse "
                "when you want one field.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=single_pass_extraction_schema(),
            handler=single_pass_extraction,
            writes=True,
            required_method="POST",
            billable=True,
            preflight=preflight_project,
        )
    )
    registry.register(
        MCPTool(
            name="extractDocument",
            description=(
                "Run a named API deployment's extraction workflow over one or "
                "more documents.\n\n"
                "**Costs money** and consumes the organization's extraction "
                "quota. Call listApiDeployments first for a valid `api_name`; "
                "the deployment fixes the prompts and output schema, so you "
                "supply documents, not instructions.\n\n"
                "The same operation is available on a deployment-scoped MCP "
                "server, where the credential reaches only one deployment. "
                "Use that one if you want a narrower blast radius.\n\n"
                f"{_ORG_WIDE_WARNING}"
            ),
            input_schema=platform_extract_document_schema(),
            handler=platform_extract_document,
            writes=True,
            required_method="POST",
            billable=True,
            # api_name is caller-supplied prose rather than an id from a
            # listing, so resolve it before the budget is claimed.
            preflight=preflight_extract_document,
        )
    )
    registry.register(
        MCPTool(
            name="getExecutionStatus",
            description=(
                "Poll for the result of an extraction started by "
                "extractDocument. Free to call.\n\n"
                "If extractDocument already returned execution_status "
                "COMPLETED, the result is in that response and no polling is "
                "needed. Otherwise poll this until COMPLETED or ERROR, "
                "pausing a few seconds between calls."
            ),
            input_schema=platform_execution_status_schema(),
            handler=get_platform_execution_status,
        )
    )

    return registry


# Registries are static, so building them once at import time is safe and keeps
# per-request work down. Kept separate rather than merged with a filter, so a
# tool cannot be exposed on the wrong server by forgetting a flag.
DEPLOYMENT_TOOLS = build_deployment_registry()
PLATFORM_TOOLS = build_platform_registry()
