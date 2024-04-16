import os
from typing import Optional

import grpc

from unstract.flags import evaluation_pb2, evaluation_pb2_grpc


class EvaluationClient:
    """A client for evaluating feature flags.

    This client communicates with an evaluation server to evaluate the state of
        a feature flag for a given entity.

    Args:
        None

    Attributes:
        channel (grpc.Channel): The gRPC channel used for communication with
            the evaluation server.
        stub (evaluation_pb2_grpc.EvaluationServiceStub):
          The gRPC stub for making requests to the evaluation server.

    Methods:
        boolean_evaluate_feature_flag: Evaluates the state of a feature flag
          for a given entity.
    """

    def __init__(self) -> None:
        """Initializes the evaluation client.

        Retrieves the evaluation server IP and port from environment variables
          and sets up the gRPC channel
        and stub for communication with the evaluation server.

        Raises:
            ValueError: If the evaluation server IP is not provided.

        Returns:
            None
        """
        evaluation_server_ip = os.environ.get("EVALUATION_SERVER_IP", "")
        evaluation_server_port = os.environ.get("EVALUATION_SERVER_PORT", "")
        print(f"evaluation_server_ip: {evaluation_server_ip}")
        print(f"evaluation_server_port: {evaluation_server_port}")

        if not evaluation_server_ip:
            raise ValueError("No response from server, refer README.md.")

        self.channel = grpc.insecure_channel(
            f"{evaluation_server_ip}:{evaluation_server_port}"
        )
        self.stub = evaluation_pb2_grpc.EvaluationServiceStub(self.channel)

    def boolean_evaluate_feature_flag(
        self,
        namespace_key: str,
        flag_key: str,
        entity_id: str,
        context: Optional[object] = None,
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
