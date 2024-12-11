"""Method is used to Evaluate a specifc feature-flag status as TRUE or FALSE.

This method sends a gRPC request to the evaluation server to determine
the state of a feature flag for a specific entity. It takes the
namespace key, flag key, entity ID, and optional context information as
input parameters.
"""

import logging
from typing import Optional

import grpc

from ..generated import evaluation_pb2, evaluation_pb2_grpc
from .base import BaseClient

logger = logging.getLogger(__name__)


class EvaluationClient(BaseClient):
    def __init__(self) -> None:
        super().__init__(evaluation_pb2_grpc.EvaluationServiceStub)

    def boolean_evaluate_feature_flag(
        self,
        namespace_key: str,
        flag_key: str,
        entity_id: str,
        context: Optional[dict] = None,
    ) -> bool:
        """Evaluates the state of a feature flag for a given entity.
        Args:
            namespace_key (str): The namespace key of the feature flag.
            flag_key (str): The key of the feature flag.
            entity_id (str): The ID of the entity for which the feature flag is
              being evaluated.
            context (object, optional): Additional context information for
                evaluating the feature flag.

        Returns:
            bool: True if the feature flag is enabled for the given entity,
              False otherwise.
        """
        try:
            request = evaluation_pb2.EvaluationRequest(
                namespace_key=namespace_key,
                flag_key=flag_key,
                entity_id=entity_id,
                context=context or {},
            )
            response = self.stub.Boolean(request)
            return bool(response.enabled)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                if self.warnings:
                    logger.warning(
                        f"Flag key {flag_key} not found in namespace {namespace_key}."
                    )
            elif e.code() == grpc.StatusCode.UNAVAILABLE:
                if self.warnings:
                    logger.warning(f"Evaluation server is unavailable: {e.details()}.")
            else:
                if self.warnings:
                    logger.warning(
                        f"Error evaluating feature flag {flag_key} for {namespace_key}"
                        f" : {str(e)}"
                    )
            return False
