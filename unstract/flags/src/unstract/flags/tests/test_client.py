import unittest
from unittest.mock import MagicMock, patch

import grpc

from unstract.flags.client import EvaluationClient


class TestEvaluationClient(unittest.TestCase):
    @patch("unstract.feature_flags.client.grpc")
    def test_boolean_evaluate_feature_flag(self, mock_grpc):
        # Mock the grpc module and create a MagicMock object for the stub
        mock_stub = MagicMock()
        mock_grpc.insecure_channel.return_value = "mock_channel"
        mock_grpc.EvaluationServiceStub.return_value = mock_stub

        # Create an instance of the EvaluationClient class
        client = EvaluationClient()

        # Mock the response from the server
        mock_response = MagicMock()
        mock_response.enabled = True
        mock_stub.Boolean.return_value = mock_response

        # Call the boolean_evaluate_feature_flag method
        result = client.boolean_evaluate_feature_flag(
            namespace_key="test_namespace",
            flag_key="test_flag",
            entity_id="test_entity",
            context={"key": "value"},
        )

        # Assert that the method returned the expected result
        self.assertTrue(result)

        # Assert that the grpc module was called with the correct arguments
        mock_grpc.insecure_channel.assert_called_once_with(
            "evaluation_SERVER_IP:EVALUATION_SERVER_PORT"
        )
        mock_grpc.EvaluationServiceStub.assert_called_once_with("mock_channel")

        # Assert that the stub's Boolean method was
        # called with the correct arguments
        mock_stub.Boolean.assert_called_once_with(
            namespace_key="test_namespace",
            flag_key="test_flag",
            entity_id="test_entity",
            context={"key": "value"},
        )

    @patch("unstract.feature_flags.client.grpc")
    def test_boolean_evaluate_feature_flag_error(self, mock_grpc):
        # Mock the grpc module and create a MagicMock object for the stub
        mock_stub = MagicMock()
        mock_grpc.insecure_channel.return_value = "mock_channel"
        mock_grpc.EvaluationServiceStub.return_value = mock_stub

        # Create an instance of the EvaluationClient class
        client = EvaluationClient()

        # Mock the RpcError when calling the stub's Boolean method
        mock_stub.Boolean.side_effect = grpc.RpcError()

        # Call the boolean_evaluate_feature_flag method
        result = client.boolean_evaluate_feature_flag(
            namespace_key="test_namespace",
            flag_key="test_flag",
            entity_id="test_entity",
            context={"key": "value"},
        )

        # Assert that the method returned False when an error occurred
        self.assertFalse(result)

        # Assert that the grpc module was called with the correct arguments
        mock_grpc.insecure_channel.assert_called_once_with(
            "evaluation_SERVER_IP:EVALUATION_SERVER_PORT"
        )
        mock_grpc.EvaluationServiceStub.assert_called_once_with("mock_channel")

        # Assert that the stub's Boolean method was called with
        # the correct arguments
        mock_stub.Boolean.assert_called_once_with(
            namespace_key="test_namespace",
            flag_key="test_flag",
            entity_id="test_entity",
            context={"key": "value"},
        )


if __name__ == "__main__":
    unittest.main()
