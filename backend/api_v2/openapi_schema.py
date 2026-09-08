"""OpenAPI annotations for the API deployment endpoints.

The serializers here shape the published spec only; none of them is used to
parse a request or build a response. They live outside ``serializers.py`` so
that nothing at request time imports one by accident.

Their docstrings are published as the client-facing model descriptions, so
they are written for the caller rather than the maintainer.
"""

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_serializer,
    extend_schema_view,
)
from platform_api.openapi_schema import PlatformKeyError
from rest_framework import serializers

from api_v2.serializers import (
    APIDeploymentListSerializer,
    APIExecutionResponseSerializer,
    ExecutionQuerySerializer,
    ExecutionRequestSerializer,
)


# Declares no field of its own, so a change to the real serializer moves the
# spec. It exists to carry a caller-facing description and a stable name.
@extend_schema_serializer(component_name="ExecuteRequest")
class ExecuteRequest(ExecutionRequestSerializer):
    """The documents to run, and the options that shape the result.

    Supply `files`, `presigned_urls`, or both.
    """


class FileResult(serializers.Serializer):
    """One input document's outcome.

    Every key is present on every item; the ones that depend on the request
    options or on the outcome are sent as `null` when they do not apply.
    """

    file = serializers.CharField()
    file_execution_id = serializers.CharField(required=False, allow_null=True)
    status = serializers.CharField(required=False)
    result = serializers.JSONField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, allow_null=True)
    extracted_text = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The document's full extracted text. Sent only when the "
        "request set `include_extracted_text`.",
    )
    error = serializers.CharField(required=False, allow_null=True)


class ExecutionMessage(APIExecutionResponseSerializer):
    """The execution's identity and, once it has finished, its per-file
    results.
    """

    # The three fields below are restated because the real serializer declares
    # them as required and non-nullable while the dataclass behind it coerces
    # every falsy value to None, so the happy path would contradict the spec.
    status_api = serializers.CharField(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)
    result = FileResult(many=True, required=False, allow_null=True)


class ExecuteResponse(serializers.Serializer):
    message = ExecutionMessage()


class StatusResponse(serializers.Serializer):
    status = serializers.CharField()
    message = FileResult(many=True, required=False, allow_null=True)


class AcknowledgedResponse(serializers.Serializer):
    """The execution's result was handed to an earlier call and discarded."""

    status = serializers.CharField()
    message = serializers.CharField()


class ErrorDetail(serializers.Serializer):
    """One problem found with the request."""

    code = serializers.CharField(help_text="Machine-readable problem identifier.")
    detail = serializers.CharField(help_text="Human-readable description.")
    attr = serializers.CharField(
        allow_null=True,
        help_text="The request field the problem belongs to, when it belongs to one.",
    )


#: Named so the generated enum is not called after the field that holds it.
ERROR_TYPES = ("validation_error", "client_error", "server_error")


class ErrorResponse(serializers.Serializer):
    """The body of a rejected request.

    Produced by the project-wide exception handler, so its shape is the same
    for every failure listed against an operation.
    """

    # `code` is left free-form rather than enumerated: the deployment
    # exceptions carry DRF's default code, not the per-status codes the
    # standardized-errors package assumes.
    type = serializers.ChoiceField(choices=ERROR_TYPES)
    errors = ErrorDetail(many=True)


# Restates the route's own pattern so a client rejects a mistyped identifier
# without a round trip.
PATH_SEGMENT = {"type": "string", "pattern": r"^[\w-]+$"}

DEPLOYMENT_PATH_PARAMETERS = [
    OpenApiParameter(
        "org_name",
        PATH_SEGMENT,
        OpenApiParameter.PATH,
        description="Organization identifier.",
    ),
    OpenApiParameter(
        "api_name",
        PATH_SEGMENT,
        OpenApiParameter.PATH,
        description="API deployment name.",
    ),
]


DEPLOYMENT_AUTH = [{"deploymentKey": []}]

# A client generated without these treats an authentication or authorization
# response as an unknown status and has nothing to branch on. The descriptions
# name what the caller can act on rather than a single cause, because a
# document store consulted during the call can surface its own status here.
DEPLOYMENT_ERRORS = {
    400: OpenApiResponse(ErrorResponse, description="The request failed validation."),
    401: OpenApiResponse(
        ErrorResponse, description="No usable API key was supplied for the deployment."
    ),
    403: OpenApiResponse(
        ErrorResponse, description="The request was refused as unauthorized."
    ),
    404: OpenApiResponse(
        ErrorResponse,
        description="No active deployment, or a referenced document, was found.",
    ),
}

# Only the execution endpoint fetches documents and takes a rate-limit slot, so
# these cannot arise on the status read.
EXECUTE_ERRORS = {
    413: OpenApiResponse(
        ErrorResponse, description="A referenced document is larger than the limit."
    ),
    429: OpenApiResponse(
        ErrorResponse, description="Too many concurrent executions; retry later."
    ),
    502: OpenApiResponse(
        ErrorResponse, description="A referenced document could not be fetched."
    ),
    504: OpenApiResponse(
        ErrorResponse, description="Fetching a referenced document timed out."
    ),
}

EXECUTE_DESCRIPTION = (
    "Execute an API deployment against one or more documents.\n\n"
    "Supply the documents either as `files` (multipart upload) or as "
    "`presigned_urls` (HTTPS S3 URLs), or both — a request carrying neither is "
    f"rejected, and the two together may not exceed "
    f"{ExecutionRequestSerializer.MAX_FILES_ALLOWED} documents.\n\n"
    "With the default `timeout` of -1 the call returns as soon as the "
    "execution is queued; read the outcome from the status endpoint."
)

STATUS_DESCRIPTION = (
    "Read the result of a previously started execution.\n\n"
    "This read is one-shot: the first call that observes a completed execution "
    "acknowledges it and the stored result is discarded, so every later call "
    "for that execution answers 406. Poll while the execution is pending, and "
    "keep the payload of the call that returns it — it cannot be fetched again."
    "\n\nA still-running execution answers 422 carrying its current `status`, "
    "so a polling loop should treat 422 as the normal reply and stop on 200. "
    "Clients that raise on any non-2xx need to allow for that."
)


# Generated clients take their command names, module paths and request shapes
# from here, so this is part of the public API surface.
DEPLOYMENT_EXECUTION_SCHEMA = extend_schema_view(
    post=extend_schema(
        operation_id="execute",
        tags=["deployment"],
        auth=DEPLOYMENT_AUTH,
        parameters=DEPLOYMENT_PATH_PARAMETERS,
        request={"multipart/form-data": ExecuteRequest},
        responses={
            200: ExecuteResponse,
            422: OpenApiResponse(
                ExecuteResponse, description="The execution finished with an error."
            ),
            500: OpenApiResponse(
                ExecuteResponse,
                description="The deployment could not be run; the body carries the "
                "execution that failed.",
            ),
            **DEPLOYMENT_ERRORS,
            **EXECUTE_ERRORS,
        },
        description=EXECUTE_DESCRIPTION,
    ),
    get=extend_schema(
        operation_id="status",
        tags=["deployment"],
        auth=DEPLOYMENT_AUTH,
        parameters=DEPLOYMENT_PATH_PARAMETERS + [ExecutionQuerySerializer],
        responses={
            200: StatusResponse,
            406: OpenApiResponse(
                AcknowledgedResponse,
                description="The result was already consumed by an earlier call.",
            ),
            422: OpenApiResponse(
                StatusResponse,
                description="The execution is still running, or it finished with an "
                "error; read `status` to tell them apart.",
            ),
            500: OpenApiResponse(
                StatusResponse,
                description="The execution could not be completed; the body carries "
                "its last known state.",
            ),
            **DEPLOYMENT_ERRORS,
        },
        description=STATUS_DESCRIPTION,
    ),
)


# Declares no field of its own, so a change to the real serializer moves the
# spec. It carries a caller-facing description and a component name the
# pagination envelope can be wrapped round without stuttering.
@extend_schema_serializer(component_name="APIDeploymentSummary")
class APIDeploymentSummary(APIDeploymentListSerializer):
    """One API deployment, as it appears in an organisation's listing.

    `api_name` and `api_endpoint` are what an execution call needs;
    `display_name` and `description` say what the deployment is for.
    """

    # The model defaults these, so DRF reports them optional --- true of a
    # request body, wrong for a response the server always fills. Left alone,
    # a generated client types them nullable and every caller writes a check
    # for a key that is always there.
    api_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


# This operation takes a platform key rather than a deployment key, so its
# credential failures come from the auth middleware in `PlatformKeyError` shape
# rather than from the project exception handler.
API_DEPLOYMENT_LIST_QUERY_PARAMETERS = [
    OpenApiParameter(
        "workflow",
        {"type": "string", "format": "uuid"},
        OpenApiParameter.QUERY,
        description="Return only the deployments of this workflow.",
    ),
    OpenApiParameter(
        "api_name",
        {"type": "string"},
        OpenApiParameter.QUERY,
        description="Return only the deployment with exactly this `api_name`.",
    ),
    OpenApiParameter(
        "search",
        {"type": "string"},
        OpenApiParameter.QUERY,
        description="Return only deployments whose display name contains this "
        "text, case-insensitively.",
    ),
]

LIST_API_DEPLOYMENTS_DESCRIPTION = (
    "List the API deployments of an organisation.\n\n"
    "Each entry carries the `api_name` and `api_endpoint` an execution call "
    "needs, alongside the `display_name` and `description` that say what the "
    "deployment is for. A key holder can therefore discover what is deployed "
    "without being told, having resolved `org_id` once from `whoami`.\n\n"
    "An entry also describes who owns the deployment and how it has been "
    "running lately, including the creator's email address. This is the same "
    "view of the organisation its own members have in the web app.\n\n"
    "The deployment's own API key is not part of this listing, so a platform "
    "key cannot be widened into the ability to execute a deployment by "
    "reading it. Executing still needs the deployment key.\n\n"
    "Results are ordered by most recent run first, then by identifier so that "
    "paging is stable. Pass `page` and `page_size`, and read `count` and "
    "`next` from the envelope."
)


API_DEPLOYMENT_LIST_SCHEMA = extend_schema_view(
    list=extend_schema(
        operation_id="list_deployments",
        tags=["deployment"],
        auth=[{"platformKey": []}],
        parameters=API_DEPLOYMENT_LIST_QUERY_PARAMETERS,
        responses={
            200: OpenApiResponse(
                APIDeploymentSummary(many=True),
                description="One page of the organisation's API deployments.",
            ),
            400: OpenApiResponse(
                ErrorResponse,
                description="A query parameter was malformed.",
            ),
            401: OpenApiResponse(
                PlatformKeyError,
                description="No usable platform API key was supplied — absent, "
                "malformed, unknown, or revoked.",
            ),
            403: OpenApiResponse(
                PlatformKeyError,
                description="The key was recognised but refused: it does not "
                "belong to the organisation named in the path, or its "
                "permission tier is not one this deployment knows.",
            ),
            500: OpenApiResponse(
                description="The request could not be served. The body is not "
                "guaranteed to be JSON.",
            ),
        },
        description=LIST_API_DEPLOYMENTS_DESCRIPTION,
    ),
)
