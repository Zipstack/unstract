"""Flipt Client class is used to interact with the Flipt server.

This contains all the methods to interact with the Flipt server like
evaluate,   list, segments and much more. This can be further extended
to add more methods to interact with the Flipt server as per the
requirement.
"""

import logging
import os

import grpc

from ..generated import flipt_pb2, flipt_pb2_grpc
from .base import BaseClient

logger = logging.getLogger(__name__)


class FliptClient(BaseClient):
    def __init__(self) -> None:
        super().__init__(flipt_pb2_grpc.FliptStub)

    def parse_flag_list(self, response):
        flags = response.flags
        total_count = response.total_count

        parsed_flags = {}
        for flag in flags:
            enabled_status = flag.enabled if hasattr(flag, "enabled") else None
            parsed_flags[flag.key] = enabled_status
        return {"flags": parsed_flags, "total_count": total_count}

    def list_feature_flags(self, namespace_key: str) -> dict:
        try:
            FLIPT_SERVICE_AVAILABLE = (
                os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() == "true"
            )
            if not FLIPT_SERVICE_AVAILABLE:
                logger.warning("Flipt service is not available.")
                return {}

            request = flipt_pb2.ListFlagRequest(namespace_key=namespace_key)
            response = self.stub.ListFlags(request)
            parsed_response = self.parse_flag_list(response)
            return parsed_response
        except grpc.RpcError as e:
            logging.error(f"Error communicating with evaluation server: {e}")
            return {}

    def evaluate_feature_flag(
        self, namespace_key: str, flag_key: str, entity_id: str, context: dict = None
    ) -> bool:
        try:
            FLIPT_SERVICE_AVAILABLE = os.environ.get("FLIPT_SERVICE_AVAILABLE", False)
            if not FLIPT_SERVICE_AVAILABLE:
                logger.warning("Flipt service is not available.")
                return False

            request = flipt_pb2.EvaluationRequest(
                namespace_key=namespace_key,
                flag_key=flag_key,
                entity_id=entity_id,
                context=context or {},
            )
            response = self.stub.Evaluate(request)
            return response.match
        except grpc.RpcError as e:
            logger.warning(
                f"Error evaluating feature flag '{flag_key}' for {namespace_key} : {e}"
            )
            return False
