import os

import grpc


class BaseClient:
    def __init__(self, stub_class) -> None:
        evaluation_server_ip = os.environ.get("EVALUATION_SERVER_IP", "")
        evaluation_server_port = os.environ.get("EVALUATION_SERVER_PORT", "")
        evaluation_server_warnings = os.environ.get(
            "EVALUATION_SERVER_WARNINGS", "false"
        )

        if not evaluation_server_ip:
            raise ValueError("No response from server, refer README.md.")

        self.channel = grpc.insecure_channel(
            f"{evaluation_server_ip}:{evaluation_server_port}"
        )
        self.stub = stub_class(self.channel)
        self.warnings = evaluation_server_warnings.lower() == "true"
