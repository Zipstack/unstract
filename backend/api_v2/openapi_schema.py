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
from rest_framework import serializers

from api_v2.serializers import (
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
    file = serializers.CharField()
    file_execution_id = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    result = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)
    metrics = serializers.JSONField(required=False)
    error = serializers.CharField(required=False, allow_null=True)


class ExecutionMessage(APIExecutionResponseSerializer):
    """The execution's identity and, once it has finished, its per-file
    results.
    """

    # Restated because the real declaration is an untyped JSONField, and
    # because a pending execution sends `result: null`, which a generated
    # deserialiser iterates and crashes on without allow_null.
    result = FileResult(many=True, required=False, allow_null=True)


class ExecuteResponse(serializers.Serializer):
    message = ExecutionMessage()


class StatusResponse(serializers.Serializer):
    status = serializers.CharField()
    message = FileResult(many=True, required=False, allow_null=True)


class ErrorResponse(serializers.Serializer):
    status = serializers.CharField(required=False)
    message = serializers.JSONField(required=False, allow_null=True)


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

# A client generated without these treats an authentication or rate-limit
# response as an unknown status and has nothing to branch on.
DEPLOYMENT_ERRORS = {
    400: OpenApiResponse(ErrorResponse, description="The request failed validation."),
    401: OpenApiResponse(ErrorResponse, description="The API key is not valid."),
    403: OpenApiResponse(ErrorResponse, description="No API key was supplied."),
    404: OpenApiResponse(ErrorResponse, description="No such active deployment."),
    429: OpenApiResponse(
        ErrorResponse, description="Too many concurrent executions; retry later."
    ),
    500: ErrorResponse,
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
            409: OpenApiResponse(
                ErrorResponse, description="The deployment has no active API key."
            ),
            422: ExecuteResponse,
            **DEPLOYMENT_ERRORS,
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
                ErrorResponse,
                description="The result was already consumed by an earlier call.",
            ),
            422: StatusResponse,
            **DEPLOYMENT_ERRORS,
        },
        description=STATUS_DESCRIPTION,
    ),
)
