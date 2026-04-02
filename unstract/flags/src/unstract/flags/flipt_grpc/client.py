"""High-level Flipt gRPC client for server-side evaluation."""

from dataclasses import dataclass

import grpc

from .flipt import flipt_simple_pb2, flipt_simple_pb2_grpc
from .flipt.evaluation import evaluation_simple_pb2, evaluation_simple_pb2_grpc


@dataclass
class GrpcClientOptions:
    """Configuration options for the Flipt gRPC client.

    Attributes:
        address: The address of the Flipt gRPC server (e.g., "localhost:9000")
        namespace_key: The namespace to use for evaluations (default: "default")
        environment_key: The environment to use for evaluations (default: "default")
        secure: Whether to use TLS/SSL for the connection (default: False)
        client_token: Optional client token for authentication
        ssl_cert_path: Optional path to SSL certificate for secure connections
    """

    address: str = "localhost:9000"
    namespace_key: str = "default"
    environment_key: str = "default"
    secure: bool = False
    client_token: str | None = None
    ssl_cert_path: str | None = None


class FliptGrpcClient:
    """High-level gRPC client for Flipt server-side evaluation.

    This client communicates with a Flipt server via gRPC to perform
    server-side flag evaluations. Unlike the FliptClient which uses
    client-side evaluation, this client makes network calls to the
    Flipt server for each evaluation.

    Example:
        ```python
        from flipt_client.grpc import FliptGrpcClient, GrpcClientOptions

        client = FliptGrpcClient(
            opts=GrpcClientOptions(address="localhost:9000", namespace_key="production")
        )

        result = client.evaluate_boolean(
            flag_key="my-flag", entity_id="user-123", context={"region": "us-west"}
        )

        print(f"Flag enabled: {result.enabled}")

        client.close()
        ```
    """

    def __init__(self, opts: GrpcClientOptions | None = None):
        """Initialize the Flipt gRPC client.

        Args:
            opts: Configuration options for the client. If None, uses defaults.
        """
        self.opts = opts or GrpcClientOptions()

        # Create the gRPC channel
        if self.opts.secure:
            if self.opts.ssl_cert_path:
                with open(self.opts.ssl_cert_path, "rb") as f:
                    credentials = grpc.ssl_channel_credentials(f.read())
            else:
                credentials = grpc.ssl_channel_credentials()
            self.channel = grpc.secure_channel(self.opts.address, credentials)
        else:
            self.channel = grpc.insecure_channel(self.opts.address)

        # Create the evaluation stub for flag evaluation
        self.stub = evaluation_simple_pb2_grpc.EvaluationServiceStub(self.channel)

        # Create the Flipt stub for management operations (like ListFlags)
        self.flipt_stub = flipt_simple_pb2_grpc.FliptStub(self.channel)

        # Set up metadata for authentication
        self.metadata = []
        if self.opts.client_token:
            self.metadata.append(("authorization", f"Bearer {self.opts.client_token}"))

    def evaluate_boolean(
        self,
        flag_key: str,
        entity_id: str,
        context: dict[str, str] | None = None,
        namespace_key: str | None = None,
        environment_key: str | None = None,
        request_id: str | None = None,
    ) -> evaluation_simple_pb2.BooleanEvaluationResponse:
        """Evaluate a boolean flag.

        Args:
            flag_key: The key of the flag to evaluate
            entity_id: The entity ID for the evaluation context
            context: Additional context for the evaluation (key-value pairs)
            namespace_key: Override the default namespace key
            environment_key: Override the default environment key
            request_id: Optional request ID for tracing

        Returns:
            BooleanEvaluationResponse containing the evaluation result

        Raises:
            grpc.RpcError: If the RPC call fails
        """
        request = evaluation_simple_pb2.EvaluationRequest(
            flag_key=flag_key,
            entity_id=entity_id,
            namespace_key=namespace_key or self.opts.namespace_key,
            environment_key=environment_key or self.opts.environment_key,
            context=context or {},
            request_id=request_id or "",
        )

        return self.stub.Boolean(request, metadata=self.metadata)

    def evaluate_variant(
        self,
        flag_key: str,
        entity_id: str,
        context: dict[str, str] | None = None,
        namespace_key: str | None = None,
        environment_key: str | None = None,
        request_id: str | None = None,
    ) -> evaluation_simple_pb2.VariantEvaluationResponse:
        """Evaluate a variant flag.

        Args:
            flag_key: The key of the flag to evaluate
            entity_id: The entity ID for the evaluation context
            context: Additional context for the evaluation (key-value pairs)
            namespace_key: Override the default namespace key
            environment_key: Override the default environment key
            request_id: Optional request ID for tracing

        Returns:
            VariantEvaluationResponse containing the evaluation result

        Raises:
            grpc.RpcError: If the RPC call fails
        """
        request = evaluation_simple_pb2.EvaluationRequest(
            flag_key=flag_key,
            entity_id=entity_id,
            namespace_key=namespace_key or self.opts.namespace_key,
            environment_key=environment_key or self.opts.environment_key,
            context=context or {},
            request_id=request_id or "",
        )

        return self.stub.Variant(request, metadata=self.metadata)

    def evaluate_batch(
        self, requests: list[dict], request_id: str | None = None
    ) -> evaluation_simple_pb2.BatchEvaluationResponse:
        """Evaluate multiple flags in a single request.

        Args:
            requests: List of evaluation requests, each containing:
                - flag_key: str
                - entity_id: str
                - context: Optional[Dict[str, str]]
                - namespace_key: Optional[str]
                - environment_key: Optional[str]
            request_id: Optional request ID for tracing

        Returns:
            BatchEvaluationResponse containing all evaluation results

        Raises:
            grpc.RpcError: If the RPC call fails
        """
        evaluation_requests = []

        for req in requests:
            evaluation_requests.append(
                evaluation_simple_pb2.EvaluationRequest(
                    flag_key=req["flag_key"],
                    entity_id=req["entity_id"],
                    namespace_key=req.get("namespace_key", self.opts.namespace_key),
                    environment_key=req.get("environment_key", self.opts.environment_key),
                    context=req.get("context", {}),
                    request_id=req.get("request_id", ""),
                )
            )

        batch_request = evaluation_simple_pb2.BatchEvaluationRequest(
            requests=evaluation_requests, request_id=request_id or ""
        )

        return self.stub.Batch(batch_request, metadata=self.metadata)

    def list_flags(
        self,
        namespace_key: str | None = None,
        environment_key: str | None = None,
        limit: int = 100,
        page_token: str | None = None,
    ) -> flipt_simple_pb2.FlagList:
        """List all flags in the namespace.

        Args:
            namespace_key: Override the default namespace key
            environment_key: Override the default environment key (required by server)
            limit: Maximum number of flags to return (default: 100)
            page_token: Token for pagination to get the next page of results

        Returns:
            FlagList containing the list of flags, next page token, and total count

        Raises:
            grpc.RpcError: If the RPC call fails

        Note:
            This method uses the flipt.Flipt service, not the evaluation service.
            The environment_key is required by the server and will default to
            self.opts.environment_key if not provided.
        """
        request = flipt_simple_pb2.ListFlagRequest(
            namespace_key=namespace_key or self.opts.namespace_key,
            environment_key=environment_key or self.opts.environment_key,
            limit=limit,
            page_token=page_token or "",
        )

        return self.flipt_stub.ListFlags(request, metadata=self.metadata)

    def close(self):
        """Close the gRPC channel and release resources."""
        if hasattr(self, "channel") and self.channel is not None:
            self.channel.close()
            self.channel = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.close()
