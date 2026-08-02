"""Extraction from the organization-scoped server.

The deployment server and this one now both run extractions. They are not
redundant: they are two blast radii for the same operation, and the caller
picks. A deployment key reaches exactly one deployment, so a leaked one costs
one workflow; the platform key reaches every deployment in the organization,
and buys the caller not having to obtain a second credential to extract at all.

The work itself is delegated to ``tools.execution`` rather than reimplemented,
so both servers share one code path through validation, rate limiting and the
execution helper. What differs is only how the target deployment is found:
there it arrives with the credential, here it is looked up by ``api_name``.

Two deliberate divergences from the deployment server:

* **No ``llm_profile_id``.** On the deployment server that argument is checked
  against the API key's owner (``ExecutionRequestSerializer.validate_llm_profile_id``).
  A platform caller is a service account with org-wide reach, so there is no
  meaningful owner to check it against, and borrowing some deployment key to
  satisfy the check would be asserting a principal this caller is not. The
  argument is therefore not offered here. This also keeps the serializer from
  ever needing the ``api_key`` that this context does not have — omitting the
  field means DRF never runs that validator.
* **Execution status is scoped to the organization.** See
  ``get_platform_execution_status``.
"""

import logging
from typing import Any

from api_v2.models import APIDeployment

from mcp_server.context import MCPContext, PlatformMCPContext
from mcp_server.exceptions import MCPToolError
from mcp_server.sanitize import valid_uuid
from mcp_server.tools.execution import (
    DEFAULT_TIMEOUT_SEC,
    extract_document,
    extract_document_schema,
)

logger = logging.getLogger(__name__)


def _resolve_deployment(context: PlatformMCPContext, api_name: str) -> APIDeployment:
    """Find an API deployment the caller may reach, or refuse.

    ``for_user`` is what keeps this inside the caller's organization. The
    platform key authenticates as a service account, for which that manager
    returns every deployment in the org — which is the intended reach here —
    but it is still the boundary that stops another organization's deployment
    being named.
    """
    deployment = (
        APIDeployment.objects.for_user(context.user).filter(api_name=api_name).first()
    )
    if deployment is None:
        raise MCPToolError(
            f"No API deployment named '{api_name}' in organization "
            f"'{context.org_name}'. Call listApiDeployments for valid names."
        )
    return deployment


def _as_deployment_context(
    context: PlatformMCPContext, deployment: APIDeployment
) -> MCPContext:
    """Adapt a platform context to the one ``tools.execution`` expects.

    ``api_key`` is deliberately ``None``. It is read in exactly one place —
    validating ``llm_profile_id`` ownership — and this tool does not accept
    that argument, so the serializer never invokes that validator. Passing a
    real deployment key instead would make the ownership check pass against
    whichever principal happens to own it, which is worse than not offering
    the feature.
    """
    return MCPContext(api=deployment, api_key=None, org_name=context.org_name)


def platform_extract_document_schema() -> dict[str, Any]:
    """The deployment schema plus ``api_name``, minus ``llm_profile_id``.

    Derived from the deployment schema rather than restated, so the two cannot
    drift on file caps, tag rules or the timeout range.
    """
    schema = extract_document_schema()
    properties = dict(schema["properties"])
    # See the module docstring: not offerable without a deployment key to check
    # ownership against.
    properties.pop("llm_profile_id", None)

    return {
        "type": "object",
        "properties": {
            "api_name": {
                "type": "string",
                "description": (
                    "Name of the API deployment to run, from "
                    "listApiDeployments. This fixes the prompts and output "
                    "schema — you supply documents, not instructions."
                ),
            },
            **properties,
        },
        "required": ["api_name", *schema["required"]],
    }


def preflight_extract_document(
    context: PlatformMCPContext, api_name: str, **_ignored: Any
) -> None:
    """Resolve the named deployment before any budget is claimed.

    ``api_name`` is the one argument here an agent can plausibly get wrong: it
    is a human-chosen string rather than an id copied from a listing, so a
    guess or a typo is likely. The budget is never refunded, so without this
    check each wrong guess would cost a billable slot for a call that reached
    no LLM at all — and an agent guessing repeatedly could exhaust the window
    without ever running an extraction.

    Extra keyword arguments are accepted and ignored so that adding an argument
    to the tool does not require touching this function; the handler is what
    validates the rest.
    """
    _resolve_deployment(context, api_name)


def platform_extract_document(
    context: PlatformMCPContext,
    api_name: str,
    document_urls: list[str],
    timeout: int = DEFAULT_TIMEOUT_SEC,
    include_metadata: bool = False,
    include_metrics: bool = False,
    include_extracted_text: bool = False,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Run a named deployment's workflow over the supplied document URLs."""
    deployment = _resolve_deployment(context, api_name)
    logger.info(
        f"MCP platform extract_document api='{api_name}' "
        f"(org '{context.org_name}', key '{context.platform_key.name}')"
    )

    result = extract_document(
        _as_deployment_context(context, deployment),
        document_urls=document_urls,
        timeout=timeout,
        include_metadata=include_metadata,
        include_metrics=include_metrics,
        include_extracted_text=include_extracted_text,
        tags=tags,
    )
    # The agent named a deployment rather than being scoped to one, so echo
    # back which one actually ran.
    return {"api_name": api_name, **result}


def platform_execution_status_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "execution_id": {
                "type": "string",
                "description": (
                    "The execution_id returned by a previous extractDocument call."
                ),
            },
            "include_metadata": {
                "type": "boolean",
                "default": False,
                "description": "Include extraction metadata in the result.",
            },
            "include_metrics": {
                "type": "boolean",
                "default": False,
                "description": "Include token and cost metrics in the result.",
            },
            "include_extracted_text": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Include the full raw text extracted from each document. "
                    "This can be very large."
                ),
            },
        },
        "required": ["execution_id"],
    }


def get_platform_execution_status(
    context: PlatformMCPContext,
    execution_id: str,
    include_metadata: bool = False,
    include_metrics: bool = False,
    include_extracted_text: bool = False,
) -> dict[str, Any]:
    """Return the status, and once ready the result, of an extraction.

    The execution id is checked against the organization *before* the status
    is fetched. ``DeploymentHelper.get_execution_status`` resolves a bare
    ``WorkflowExecution.objects.get(id=...)`` with no tenant filter, and this
    deployment runs a single shared schema rather than one per tenant, so
    without this check a caller could poll an execution id belonging to
    another organization.

    ``get_execution_status`` makes the equivalent check on the deployment
    server, anchored to that deployment's single workflow. The two differ only
    in width: a platform key reaches every workflow in the org, so the filter
    here is ``workflow_id__in=visible`` rather than one id.
    """
    from workflow_manager.workflow_v2.models.execution import WorkflowExecution

    from mcp_server.tools.execution import get_execution_status
    from mcp_server.tools.observability import _org_workflow_ids

    valid_uuid(execution_id, "execution id", "Poll only ids returned by extractDocument.")

    visible = _org_workflow_ids(context)
    execution = (
        WorkflowExecution.objects.filter(id=execution_id, workflow_id__in=visible)
        .only("id", "pipeline_id")
        .first()
    )
    if execution is None:
        raise MCPToolError(
            f"No execution with id '{execution_id}' in organization "
            f"'{context.org_name}'. Poll only ids returned by extractDocument, "
            "or call listExecutions."
        )

    # Resolve by `pipeline_id` — the deployment that actually started this run —
    # not by the workflow. `APIDeployment.workflow` has no uniqueness
    # constraint, so a workflow-based lookup returns an arbitrary one of the
    # deployments sharing it, and `get_execution_status` then scopes its own
    # check to *that* deployment and rejects an execution the caller legitimately
    # owns. Going straight to the recorded deployment also drops a hop.
    deployment = (
        APIDeployment.objects.for_user(context.user)
        .filter(id=execution.pipeline_id)
        .first()
    )
    if deployment is None:
        raise MCPToolError(
            f"Execution '{execution_id}' did not come from an API deployment. "
            "Use getExecutionDetail for pipeline and ETL runs."
        )

    return get_execution_status(
        _as_deployment_context(context, deployment),
        execution_id=execution_id,
        include_metadata=include_metadata,
        include_metrics=include_metrics,
        include_extracted_text=include_extracted_text,
    )
