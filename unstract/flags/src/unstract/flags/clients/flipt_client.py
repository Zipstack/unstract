import grpc
import logging
from .base_client import BaseClient
from ..generated import flipt_pb2, flipt_pb2_grpc

class FliptClient(BaseClient):
    def __init__(self):
        super().__init__(flipt_pb2_grpc.FliptStub())

    def list_feature_flags(self, namespace_key: str) -> dict:
        try:
            request = flipt_pb2.ListFlagRequest(namespace_key=namespace_key)
            response = self.stub.ListFlags(request)
            logging.info(f"************* Evaluation Response : {response}")
            return response
        except grpc.RpcError as e:
            logging.error(f"Error communicating with evaluation server: {e}")
            return {}
