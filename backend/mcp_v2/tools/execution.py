"""Tools that run the connected API deployment and read back its results."""

import logging
import uuid
from typing import Any

from api_v2.constants import ApiExecution
from api_v2.deployment_helper import DeploymentHelper
from api_v2.dto import DeploymentExecutionDTO
from api_v2.exceptions import RateLimitExceeded
from api_v2.rate_limiter import APIDeploymentRateLimiter
from api_v2.serializers import ExecutionQuerySerializer, ExecutionRequestSerializer
from rest_framework.exceptions import ValidationError
from tags.serializers import TagParamsSerializer
from utils.enums import CeleryTaskState
from workflow_manager.workflow_v2.dto import ExecutionResponse

from mcp_v2.context import MCPContext
from mcp_v2.exceptions import MCPToolError

logger = logging.getLogger(__name__)

# Mirrors the serializer limits into the JSON schema, so a well-behaved client
# is stopped before it spends a round trip on a request that cannot validate.
# Sourced from the serializers rather than copied, so the advertised schema
# tracks the limits actually enforced.
MAX_DOCUMENTS = ExecutionRequestSerializer.MAX_FILES_ALLOWED
MAX_TAGS = TagParamsSerializer.MAX_TAGS_ALLOWED

# An agent polling with getExecutionStatus does not benefit from holding the
# HTTP request open for the full 300s the REST API permits, and a long-held
# MCP call reads as a hang. Default to a short wait and let the agent poll.
DEFAULT_TIMEOUT_SEC = 30


def _format_validation_error(error: ValidationError) -> str:
    """Flatten DRF validation detail into a sentence an agent can act on.

    ``error.detail`` stringifies with ``ErrorDetail(string=..., code=...)``
    wrappers and nested dict/list structure. That is noise the agent has to
    parse around before it can see which argument was wrong, so flatten it to
    ``field: message`` pairs.
    """

    def walk(node: Any, path: str = "") -> list[str]:
        if isinstance(node, dict):
            return [
                message
                for key, value in node.items()
                for message in walk(value, f"{path}.{key}" if path else str(key))
            ]
        if isinstance(node, list):
            return [message for item in node for message in walk(item, path)]
        return [f"{path}: {node}" if path else str(node)]

    return "; ".join(walk(error.detail))


def extract_document_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "document_urls": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": MAX_DOCUMENTS,
                "description": (
                    "S3 pre-signed URLs of the documents to extract. Unstract "
                    "fetches these server-side. Only S3 pre-signed URLs are "
                    "accepted — an ordinary public http(s) link is rejected."
                ),
            },
            "timeout": {
                "type": "integer",
                "minimum": -1,
                "maximum": ApiExecution.MAXIMUM_TIMEOUT_IN_SEC,
                "default": DEFAULT_TIMEOUT_SEC,
                "description": (
                    "Seconds to wait for the extraction to finish before "
                    "returning a pending result. Use -1 to return immediately "
                    "and poll with getExecutionStatus."
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
                    "Include the full raw text extracted from each document, "
                    "alongside the structured output. This can be very large."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_TAGS,
                "description": (
                    f"Tags to associate with this execution (at most "
                    f"{MAX_TAGS}). Each tag must start with a letter and "
                    "contain only letters, numbers, underscores and hyphens."
                ),
            },
            "llm_profile_id": {
                "type": "string",
                "description": (
                    "UUID of an LLM profile to override the deployment's "
                    "default. Omit to use the configured default."
                ),
            },
        },
        "required": ["document_urls"],
    }


def extract_document(
    context: MCPContext,
    document_urls: list[str],
    timeout: int = DEFAULT_TIMEOUT_SEC,
    include_metadata: bool = False,
    include_metrics: bool = False,
    include_extracted_text: bool = False,
    tags: list[str] | None = None,
    llm_profile_id: str | None = None,
) -> dict[str, Any]:
    """Run the deployment's workflow over the supplied document URLs.

    Deliberately routed through ``ExecutionRequestSerializer`` rather than
    calling the execution helper directly: that serializer owns URL validation
    (HTTPS/endpoint restrictions) and the file-count cap, and reimplementing
    those here would let the MCP surface drift away from the REST surface it
    is meant to mirror.
    """
    if not context.api.is_active:
        raise MCPToolError(
            f"API deployment '{context.api.display_name}' is not active. "
            "Activate it in Unstract before extracting."
        )

    # `tags` is a comma-separated string on the REST surface; MCP clients
    # produce JSON arrays, so convert rather than exposing the wire format.
    payload: dict[str, Any] = {
        ApiExecution.PRESIGNED_URLS: document_urls,
        ApiExecution.TIMEOUT_FORM_DATA: timeout,
        ApiExecution.INCLUDE_METADATA: include_metadata,
        ApiExecution.INCLUDE_METRICS: include_metrics,
        ApiExecution.INCLUDE_EXTRACTED_TEXT: include_extracted_text,
    }
    if tags:
        payload[ApiExecution.TAGS] = ",".join(tags)
    if llm_profile_id:
        payload[ApiExecution.LLM_PROFILE_ID] = llm_profile_id

    serializer = ExecutionRequestSerializer(
        data=payload, context={"api": context.api, "api_key": context.api_key}
    )
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as error:
        raise MCPToolError(
            f"Invalid arguments: {_format_validation_error(error)}"
        ) from error

    validated = serializer.validated_data
    presigned_urls = validated.get(ApiExecution.PRESIGNED_URLS, [])

    organization = context.api.organization
    execution_id = str(uuid.uuid4())

    # Take the rate-limit slot before downloading anything. The REST view
    # fetches first because it already holds the uploaded files in the request
    # body; here the fetch is ours to make, and doing it for a call we are
    # about to reject would pull every document over the network for nothing.
    can_proceed, limit_info = APIDeploymentRateLimiter.check_and_acquire(
        organization, execution_id
    )
    if not can_proceed:
        raise MCPToolError(
            "Rate limit exceeded for this organization "
            f"({limit_info['current_usage']}/{limit_info['limit']} "
            f"{limit_info['limit_type']}). Retry once running extractions finish."
        )

    try:
        file_objs: list[Any] = []
        DeploymentHelper.load_presigned_files(presigned_urls, file_objs)
        response = DeploymentHelper.execute_workflow(
            organization_name=context.org_name,
            api=context.api,
            file_objs=file_objs,
            timeout=validated.get(ApiExecution.TIMEOUT_FORM_DATA),
            include_metadata=validated.get(ApiExecution.INCLUDE_METADATA),
            include_metrics=validated.get(ApiExecution.INCLUDE_METRICS),
            include_extracted_text=validated.get(ApiExecution.INCLUDE_EXTRACTED_TEXT),
            use_file_history=validated.get(ApiExecution.USE_FILE_HISTORY, False),
            tag_names=validated.get(ApiExecution.TAGS, []),
            llm_profile_id=validated.get(ApiExecution.LLM_PROFILE_ID),
            execution_id=execution_id,
        )
    except RateLimitExceeded as error:
        # A limit raised from deeper in the stack is a different limit than the
        # one checked above, but it is still the agent's to wait out — so
        # convert it rather than letting it fall through to the generic
        # "failed unexpectedly" branch below.
        APIDeploymentRateLimiter.release_slot(organization, execution_id)
        raise MCPToolError(
            f"Rate limit exceeded: {error.detail}. Retry once running extractions finish."
        ) from error
    except Exception as error:
        APIDeploymentRateLimiter.release_slot(organization, execution_id)
        logger.exception(
            f"MCP extractDocument failed for api '{context.api.api_name}': {error}"
        )
        raise MCPToolError(f"Extraction failed: {error}") from error

    result = dict(response)
    # Surface the execution id unconditionally. On the pending path it is the
    # agent's only handle for polling, and execute_workflow does not guarantee
    # it is present in the response body.
    result.setdefault("execution_id", execution_id)
    return result


def get_execution_status_schema() -> dict[str, Any]:
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


def get_execution_status(
    context: MCPContext,
    execution_id: str,
    include_metadata: bool = False,
    include_metrics: bool = False,
    include_extracted_text: bool = False,
) -> dict[str, Any]:
    """Return the status, and once ready the result, of an extraction."""
    serializer = ExecutionQuerySerializer(
        data={
            ApiExecution.EXECUTION_ID: execution_id,
            ApiExecution.INCLUDE_METADATA: include_metadata,
            ApiExecution.INCLUDE_METRICS: include_metrics,
            ApiExecution.INCLUDE_EXTRACTED_TEXT: include_extracted_text,
        }
    )
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as error:
        raise MCPToolError(
            f"Invalid arguments: {_format_validation_error(error)}"
        ) from error

    validated = serializer.validated_data
    response: ExecutionResponse = DeploymentHelper.get_execution_status(
        validated.get(ApiExecution.EXECUTION_ID)
    )

    if response.result_acknowledged:
        # The REST surface answers 406 here. An agent cannot act on a status
        # code, so say plainly that the result is gone and not retrievable.
        return {
            "execution_status": response.execution_status,
            "message": (
                "This result was already acknowledged and is no longer "
                "retrievable. Start a new extraction if you need it again."
            ),
        }

    if response.execution_status == CeleryTaskState.COMPLETED.value:
        deployment_execution_dto = DeploymentExecutionDTO(
            api=context.api, api_key=context.api_key
        )
        DeploymentHelper.process_completed_execution(
            response=response,
            deployment_execution_dto=deployment_execution_dto,
            include_metadata=validated.get(ApiExecution.INCLUDE_METADATA),
            include_metrics=validated.get(ApiExecution.INCLUDE_METRICS),
            include_extracted_text=validated.get(ApiExecution.INCLUDE_EXTRACTED_TEXT),
        )

    return {
        "execution_id": execution_id,
        "execution_status": response.execution_status,
        "result": response.result,
    }
