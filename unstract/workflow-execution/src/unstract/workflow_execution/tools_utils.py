import logging
import os
from typing import Any, Optional

from redis import Redis
from unstract.tool_registry import ToolRegistry
from unstract.tool_sandbox import ToolSandbox
from unstract.workflow_execution.constants import ToolExecution
from unstract.workflow_execution.constants import ToolRuntimeVariable as ToolRV
from unstract.workflow_execution.dto import ToolInstance, WorkflowDto
from unstract.workflow_execution.exceptions import (
    BadRequestException,
    MissingEnvVariable,
    ToolExecutionException,
    ToolNotFoundException,
)
from unstract.workflow_execution.pubsub_helper import LogHelper

logger = logging.getLogger(__name__)


class ToolsUtils:
    def __init__(
        self,
        redis: "Redis[Any]",
        organization_id: str,
        workflow: WorkflowDto,
        platform_service_api_key: str,
        ignore_processed_entities: bool = False,
    ) -> None:
        self.redis = redis
        self.tool_registry = ToolRegistry()
        self.organization_id = organization_id
        self.platform_service_api_key = platform_service_api_key
        self.workflow_id = workflow.id
        self.ignore_processed_entities = ignore_processed_entities
        self.messaging_channel: Optional[str] = None
        self.platform_service_host = ToolsUtils.get_env(
            ToolRV.PLATFORM_HOST, raise_exception=True
        )
        self.platform_service_port = ToolsUtils.get_env(
            ToolRV.PLATFORM_PORT, raise_exception=True
        )
        self.doc_processor_url = ToolsUtils.get_env(
            ToolRV.DOCUMENT_PROCESSOR_URL, raise_exception=True
        )
        self.doc_processor_api_key = ToolsUtils.get_env(
            ToolRV.DOCUMENT_PROCESSOR_API_KEY, raise_exception=True
        )
        self.prompt_host = ToolsUtils.get_env(
            ToolRV.PROMPT_HOST, raise_exception=True
        )
        self.prompt_port = ToolsUtils.get_env(
            ToolRV.PROMPT_PORT, raise_exception=True
        )
        self.x2text_host = ToolsUtils.get_env(
            ToolRV.X2TEXT_HOST, raise_exception=True
        )
        self.x2text_port = ToolsUtils.get_env(
            ToolRV.X2TEXT_PORT, raise_exception=True
        )

    def set_messaging_channel(self, messaging_channel: str) -> None:
        self.messaging_channel = messaging_channel

    def load_tools(
        self, tool_instances: list[ToolInstance]
    ) -> dict[str, dict[str, Any]]:
        """Load and check all required tools.

        Args:
            tool_instances (list[dict[str, Any]]): list of tool instances

        Raises:
            ToolNotFoundException: _description_

        Returns:
            dict[str, dict[str, Any]]: tools
        """
        tool_uids = [tool_instance.tool_id for tool_instance in tool_instances]
        tools: dict[
            str, dict[str, Any]
        ] = self.tool_registry.get_available_tools(tool_uids)
        if not (
            all(tool_uid in tools for tool_uid in tool_uids)
            and len(tool_uids) == len(tools)
        ):
            raise ToolNotFoundException
        return tools

    def check_to_build(
        self, tools: list[ToolInstance], execution_id: str
    ) -> list[ToolSandbox]:
        """_summary_

        Args:
            tools (list[dict[str, Any]]): workflow_tools in the step order
            [
                {
                    tool_instance:{id: .., meta_data:..}
                },
                ..
            ]
        """
        tool_sandboxes: list[ToolSandbox] = []
        for tool_instance in tools:
            self.validate_tool_instance(tool_instance)

            tool_uid = tool_instance.tool_id

            LogHelper.publish(
                self.messaging_channel,
                LogHelper.log(
                    "BUILD",
                    f"------ Building step {tool_instance.step}/{tool_uid}",
                ),
            )

            tool_envs = self.get_tool_environment_variables()
            logger.info(f"Tool Environments are collected for tool {tool_uid}")
            image_name = tool_instance.image_name
            image_tag = tool_instance.image_tag

            LogHelper.publish(
                self.messaging_channel,
                LogHelper.log("BUILD", f"Building the tool {tool_uid} now..."),
            )
            tool_sandbox = ToolSandbox(
                organization_id=self.organization_id,
                workflow_id=self.workflow_id,
                execution_id=execution_id,
                tool_guid=tool_uid,
                tool_instance_id=tool_instance.id,
                image_name=image_name,
                image_tag=image_tag,
                environment_variables=tool_envs,
                messaging_channel=self.messaging_channel,
            )
            tool_sandbox.set_tool_instance_settings(tool_instance.metadata)
            tool_sandboxes.append(tool_sandbox)
        return tool_sandboxes

    def validate_tool_instance(self, tool_instance: ToolInstance) -> None:
        if not tool_instance:
            raise BadRequestException("Tool instance not found")
        if not tool_instance.properties:
            raise ToolExecutionException("Properties not found in instance")
        if not tool_instance.image_name:
            raise ToolExecutionException("Image not found in instance")

    def check_tools_are_available(self, tool_ids: list[str]) -> bool:
        """Check the tools are available in platform.

        Args:
            tool_ids (list[str]): list of tool uids

        Raises:
            ToolNotFoundException: Tool Not Found

        Returns:
            bool: status
        """
        for tool_id in tool_ids:
            if not self.tool_registry.is_image_available(tool_id):
                raise ToolNotFoundException

        return True

    def run_tool(
        self,
        tool_sandbox: ToolSandbox,
    ) -> Any:
        return self.run_tool_with_retry(tool_sandbox)

    def run_tool_with_retry(
        self,
        tool_sandbox: ToolSandbox,
        max_retries: int = ToolExecution.MAXIMUM_RETRY,
    ) -> Any:
        error: Optional[dict[str, Any]] = None
        for retry_count in range(max_retries):
            try:
                response = tool_sandbox.run_tool()
                if response:
                    result: dict[str, Any] = response.get("result", {})
                    return result
                logger.warning(
                    f"ToolExecutionException - Retrying "
                    f"({retry_count + 1}/{max_retries})"
                )
            except Exception as e:
                logger.warning(
                    f"Exception - Retrying ({retry_count + 1}/{max_retries}): "
                    f"{str(e)}"
                )

        logger.warning(
            f"Operation failed after {max_retries} " f"retries, error: {error}"
        )
        return None

    def get_tool_environment_variables(
        self, project_settings: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Obtain a dictionary of env variables required by a tool.

        This combines the user defined envs (coming from project_settings)
        as well as the env variables that are platform specific into
        one key-value store.

        Args:
            project_settings (Optional[dict[str, Any]]): User defined settings

        Returns:
            dict[str, Any]: Dict of env variables for a tool
        """
        platform_vars = {
            ToolRV.PLATFORM_HOST: self.platform_service_host,
            ToolRV.PLATFORM_PORT: self.platform_service_port,
            ToolRV.PLATFORM_SERVICE_API_KEY: self.platform_service_api_key,
            ToolRV.DOCUMENT_PROCESSOR_URL: self.doc_processor_url,
            ToolRV.DOCUMENT_PROCESSOR_API_KEY: self.doc_processor_api_key,
            ToolRV.PROMPT_HOST: self.prompt_host,
            ToolRV.PROMPT_PORT: self.prompt_port,
            ToolRV.X2TEXT_HOST: self.x2text_host,
            ToolRV.X2TEXT_PORT: self.x2text_port,
        }
        if not project_settings:
            project_settings = {}
        return {**project_settings, **platform_vars}

    @staticmethod
    def get_env(env_key: str, raise_exception: bool = False) -> Optional[str]:
        """Gets the value against an environment variable.

        Args:
            env_key (str): Env to retrieve for
            raise_exception (bool, optional): Flag to raise an exception.
                Defaults to False.

        Raises:
            MissingEnvVariable: Exception if a required env is missing

        Returns:
            Optional[str]: Value for the env variable
        """
        env_value = os.environ.get(env_key)
        if (env_value is None or env_value == "") and raise_exception:
            raise MissingEnvVariable(f"Env variable {env_key} is required")
        return env_value
