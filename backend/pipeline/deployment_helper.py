import logging
from functools import wraps
from typing import Any

from api.exceptions import APINotFound, Forbidden, InactiveAPI, UnauthorizedKey
from api.key_helper import KeyHelper
from django.urls import reverse
from django_tenants.utils import get_tenant_model, tenant_context
from pipeline.pipeline_processor import PipelineProcessor
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class DeploymentHelper:
    @staticmethod
    def validate_api_key(func: Any) -> Any:
        """Decorator that validates the API key.

        Sample header:
            Authorization: Bearer 123e4567-e89b-12d3-a456-426614174001
        Args:
            func (Any): Function to wrap for validation
        """

        @wraps(func)
        def wrapper(self: Any, request: Request, *args: Any, **kwargs: Any) -> Any:
            """Wrapper to validate the inputs and key.

            Args:
                request (Request): Request context

            Raises:
                Forbidden: _description_
                APINotFound: _description_

            Returns:
                Any: _description_
            """
            try:
                authorization_header = request.headers.get("Authorization")
                api_key = None
                if authorization_header and authorization_header.startswith("Bearer "):
                    api_key = authorization_header.split(" ")[1]
                if not api_key:
                    raise Forbidden("Missing api key")
                org_name = kwargs.get("org_name") or request.data.get("org_name")
                pipeline_id = kwargs.get("pipeline_id") or request.data.get(
                    "pipeline_id"
                )
                if not pipeline_id:
                    expected_url = reverse(
                        "pipeline_api_deployment_execution",
                        kwargs={
                            "org_name": "<org_name>",
                            "pipeline_id": "<pipeline_id>",
                        },
                    )
                    url = expected_url.replace("<org_name>", "org_name").replace(
                        "<pipeline_id>", "pipeline_id"
                    )
                    raise Forbidden(
                        "Missing pipeline_id in API. The API should follow the "
                        f"structure: {url}"
                    )
                tenant = get_tenant_model().objects.get(schema_name=org_name)
                with tenant_context(tenant):
                    pipeline = PipelineProcessor.fetch_pipeline(
                        pipeline_id=pipeline_id, check_active=True
                    )
                    KeyHelper.validate_api_key(api_key=api_key, instance=pipeline)
                    kwargs["pipeline"] = pipeline
                    return func(self, request, *args, **kwargs)
            except (UnauthorizedKey, InactiveAPI, APINotFound):
                raise
            except Exception as exception:
                logger.error(f"Exception: {exception}")
                return Response(
                    {"error": str(exception)}, status=status.HTTP_403_FORBIDDEN
                )

        return wrapper
