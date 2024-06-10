from typing import Optional
import grpc

from .base_client import BaseClient
from ..generated import evaluation_pb2, evaluation_pb2_grpc

class EvaluationClient(BaseClient):
    def __init__(self) -> None:
        super().__init__(evaluation_pb2_grpc.EvaluationServiceStub)

    def list_flags(
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
            print(f"Error communicating with evaluation server: {e}")
            return False