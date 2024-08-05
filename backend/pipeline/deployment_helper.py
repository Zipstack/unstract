import logging
from typing import Any

from api.api_key_validator import BaseAPIKeyValidator
from api.exceptions import Forbidden
from api.key_helper import KeyHelper
from pipeline.pipeline_processor import PipelineProcessor
from rest_framework.request import Request

logger = logging.getLogger(__name__)


class DeploymentHelper(BaseAPIKeyValidator):
    @staticmethod
    def validate_specific_parameters(request: Request, **kwargs: Any) -> None:
        """Validate pipeline_id for pipeline deployments."""
        pipeline_id = kwargs.get("pipeline_id") or request.data.get("pipeline_id")
        if not pipeline_id:
            raise Forbidden("Missing pipeline_id in API")

    @staticmethod
    def validate_and_process(
        self: Any, request: Request, func: Any, api_key: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Fetch pipeline and validate API key."""
        pipeline_id = kwargs.get("pipeline_id") or request.data.get("pipeline_id")
        pipeline = PipelineProcessor.fetch_pipeline(
            pipeline_id=pipeline_id, check_active=True
        )
        KeyHelper.validate_api_key(api_key=api_key, instance=pipeline)
        kwargs["pipeline"] = pipeline
        return func(self, request, *args, **kwargs)
