from typing import Optional
import grpc

from .base_client import BaseClient
from ..generated import flipt_pb2, flipt_pb2_grpc

class FliptClient(BaseClient):
    def __init__(self) -> None:
        super().__init__(flipt_pb2_grpc.FliptStub) 

    def boolean_evaluate_feature_flag(
        self,
        namespace_key: str,
        flag_key: str,
        entity_id: str,
        context: Optional[dict] = None,
    ) -> bool:
        try:
            request = flipt_pb2.EvaluationRequest(
                flag_key=flag_key,
                entity_id=entity_id,
                context={},
                namespace_key=namespace_key,
            )
            request = flipt_pb2.ListFlagRequest(namespace_key=namespace_key)
            response = self.stub.ListFlags(request)
            print(f"************* Evaluation Response for flag {flag_key}: {response}")
            return response
        except grpc.RpcError as e:
            print(f"Error communicating with evaluation server: {e}")
            return False
