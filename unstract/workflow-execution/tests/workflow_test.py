import json
import unittest
from unittest.mock import Mock, patch

from unstract.workflow.dto import ConnectorInstance, ToolInstance, ToolSettings
from unstract.workflow.enums import ExecutionType
from unstract.workflow.workflow import Workflow


def get_mock_tool_instances() -> list[ToolInstance]:
    with open("sample_instances.json") as file:
        tool_instance_data = json.load(file)
    return [
        ToolInstance(
            id=item["id"],
            tool_id=item["tool_id"],
            workflow=item["workflow"],
            input=item["input"],
            output=item["output"],
            metadata=item["metadata"],
            input_file_connector=ConnectorInstance(**item["input_file_connector"]),
            output_file_connector=ConnectorInstance(**item["output_file_connector"]),
            input_db_connector=ConnectorInstance(**item["input_db_connector"]),
            output_db_connector=ConnectorInstance(**item["output_db_connector"]),
            tool_settings=ToolSettings(**item["tool_settings"]),
        )
        for item in tool_instance_data
    ]


class TestWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_env = {
            "REDIS_HOST": "mock_redis_host",
            "REDIS_PORT": "6379",
            "REDIS_USER": "mock_redis_user",
            "REDIS_PASSWORD": "mock_redis_password",
        }

    def tearDown(self) -> None:
        pass

    @patch.dict(
        "os.environ",
        {
            "REDIS_HOST": "mock_redis_host",
            "REDIS_PORT": "6379",
            "REDIS_USER": "mock_redis_user",
            "REDIS_PASSWORD": "mock_redis_password",
        },
    )
    def test_compile_workflow_success(self) -> None:
        mock_tool_instances = get_mock_tool_instances()
        mock_tool_utils = Mock()
        mock_step_metadata = {"step": "metadata"}

        mock_tool_utils.validate_tool_instance_with_tools.return_value = [
            mock_step_metadata
        ]

        workflow = Workflow(
            workflow_id="workflow_id",
            project_id="project_id",
            tool_instances=mock_tool_instances,
        )
        workflow.tool_utils = mock_tool_utils

        result = workflow.compile_workflow(execution_id="execution_id")

        self.assertEqual(result, {"workflow": "workflow_id", "success": True})
        mock_tool_utils.validate_tool_instance_with_tools.assert_called_once_with(
            tool_instances=mock_tool_instances
        )

    @patch.dict(
        "os.environ",
        {
            "REDIS_HOST": "mock_redis_host",
            "REDIS_PORT": "6379",
            "REDIS_USER": "mock_redis_user",
            "REDIS_PASSWORD": "mock_redis_password",
        },
    )
    def test_compile_workflow_failure(self) -> None:
        mock_tool_instances = get_mock_tool_instances()
        mock_tool_utils = Mock()

        mock_tool_utils.validate_tool_instance_with_tools.side_effect = Exception(
            "Test error message"
        )

        workflow = Workflow(
            workflow_id="workflow_id",
            project_id="project_id",
            tool_instances=mock_tool_instances,
        )
        workflow.tool_utils = mock_tool_utils

        result = workflow.compile_workflow(execution_id="execution_id")

        self.assertEqual(
            result,
            {
                "workflow": "workflow_id",
                "problems": ["Test error message"],
                "success": False,
            },
        )
        mock_tool_utils.validate_tool_instance_with_tools.assert_called_once_with(
            tool_instances=mock_tool_instances
        )

    @patch.dict(
        "os.environ",
        {
            "REDIS_HOST": "mock_redis_host",
            "REDIS_PORT": "6379",
            "REDIS_USER": "mock_redis_user",
            "REDIS_PASSWORD": "mock_redis_password",
        },
    )
    def test_build_workflow(self) -> None:
        mock_step_metadata = {"step": "metadata"}
        mock_tool_utils = Mock()
        mock_tool_utils.check_to_build.return_value = [mock_step_metadata]

        workflow = Workflow(
            workflow_id="workflow_id",
            project_id="project_id",
            tool_instances=[],
        )
        workflow.tool_utils = mock_tool_utils

        workflow.build_workflow()

        self.assertEqual(workflow.tool_sandboxes, [mock_step_metadata])
        mock_tool_utils.check_to_build.assert_called_once_with([])

    # @patch.dict(
    #     "os.environ",
    #     {
    #         "REDIS_HOST": "mock_redis_host",
    #         "REDIS_PORT": "6379",
    #         "REDIS_USER": "mock_redis_user",
    #         "REDIS_PASSWORD": "mock_redis_password",
    #     },
    # )

    # Commenting now due to type issue
    # def test_execute_workflow_complete(self) -> None:
    #     mock_tool_instances = get_mock_tool_instances()
    #     mock_tool_utils = Mock()
    #     mock_step_metadata: list[ToolInstance] = [
    #         {"tool_instance": tool_instance, "sandbox": Mock()}
    #         for tool_instance in mock_tool_instances
    #     ]
    #     mock_workflow = Workflow(
    #         workflow_id="workflow_id",
    #         project_id="project_id",
    #         tool_instances=mock_tool_instances,
    #     )
    #     mock_workflow.tool_utils = mock_tool_utils
    #     mock_workflow.compiled_step_metadata = mock_step_metadata
    #     mock_workflow.execution_id = "execution_id"
    #     mock_workflow.execute_workflow(execution_type=ExecutionType.COMPLETE)

    @patch.dict(
        "os.environ",
        {
            "REDIS_HOST": "mock_redis_host",
            "REDIS_PORT": "6379",
            "REDIS_USER": "mock_redis_user",
            "REDIS_PASSWORD": "mock_redis_password",
        },
    )
    @patch("redis.Redis", Mock)
    def test_execute_workflow_no_execution_id(self) -> None:
        mock_tool_instances = get_mock_tool_instances()
        mock_tool_utils = Mock()
        mock_workflow = Workflow(
            workflow_id="workflow_id",
            project_id="project_id",
            tool_instances=mock_tool_instances,
        )
        mock_workflow.tool_utils = mock_tool_utils
        mock_workflow.execution_id = "mock_execution_id"

        mock_workflow.execute_workflow(execution_type=ExecutionType.COMPLETE)

    @patch.dict(
        "os.environ",
        {
            "REDIS_HOST": "mock_redis_host",
            "REDIS_PORT": "6379",
            "REDIS_USER": "mock_redis_user",
            "REDIS_PASSWORD": "mock_redis_password",
        },
    )
    @patch("redis.Redis", Mock)
    def test_execute_tool(self) -> None:
        mock_input_format = {"input_key": "input_value"}
        mock_instance_settings = {"setting_key": "setting_value"}
        execution_type = ExecutionType.COMPLETE
        execution_id = "execution_id"
        mock_tool_sandbox = Mock()

        mock_tool_utils = Mock()
        mock_tool_utils.run_tool.return_value = ["output_data1", "output_data2"]

        mock_workflow = Workflow(
            workflow_id="workflow_id",
            project_id="project_id",
            tool_instances=[],
        )
        mock_workflow.tool_utils = mock_tool_utils

        output = mock_workflow.execute_tool(
            execution_type=execution_type,
            execution_id=execution_id,
            input_format=mock_input_format,
            instance_settings=mock_instance_settings,
            tool_sandbox=mock_tool_sandbox,
        )

        self.assertEqual(output, ["output_data1", "output_data2"])
        mock_tool_utils.run_tool.assert_called_once_with(
            input_format=mock_input_format,
            instance_settings=mock_instance_settings,
            tool_input=None,
            tool_sandbox=mock_tool_sandbox,
        )


if __name__ == "__main__":
    unittest.main()
