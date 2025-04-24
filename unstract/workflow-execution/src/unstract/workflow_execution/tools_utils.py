import logging
import os
from typing import Any

from redis import Redis

from unstract.core.pubsub_helper import LogPublisher
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
        self.messaging_channel: str | None = None
        self.platform_service_host = ToolsUtils.get_env(
            ToolRV.PLATFORM_HOST, raise_exception=True
        )
        self.platform_service_port = ToolsUtils.get_env(
            ToolRV.PLATFORM_PORT, raise_exception=True
        )
        self.prompt_host = ToolsUtils.get_env(ToolRV.PROMPT_HOST, raise_exception=True)
        self.prompt_port = ToolsUtils.get_env(ToolRV.PROMPT_PORT, raise_exception=True)
        self.x2text_host = ToolsUtils.get_env(ToolRV.X2TEXT_HOST, raise_exception=True)
        self.x2text_port = ToolsUtils.get_env(ToolRV.X2TEXT_PORT, raise_exception=True)
        self.llmw_poll_interval = ToolsUtils.get_env(
            ToolRV.ADAPTER_LLMW_POLL_INTERVAL, raise_exception=False
        )
        self.llmw_max_polls = ToolsUtils.get_env(
            ToolRV.ADAPTER_LLMW_MAX_POLLS, raise_exception=False
        )
        self.llmw_wait_timeout = ToolsUtils.get_env(
            ToolRV.ADAPTER_LLMW_WAIT_TIMEOUT, raise_exception=False
        )
        self.redis_host = ToolsUtils.get_env(ToolRV.REDIS_HOST, raise_exception=True)
        self.redis_port = ToolsUtils.get_env(ToolRV.REDIS_PORT, raise_exception=True)
        self.redis_user = ToolsUtils.get_env(ToolRV.REDIS_USER, raise_exception=True)
        self.redis_password = ToolsUtils.get_env(
            ToolRV.REDIS_PASSWORD, raise_exception=True
        )

    def set_messaging_channel(self, messaging_channel: str) -> None:
        self.messaging_channel = messaging_channel

    def load_tools(self, tool_instances: list[ToolInstance]) -> dict[str, dict[str, Any]]:
        """Load and check all required tools.

        Args:
            tool_instances (list[dict[str, Any]]): list of tool instances

        Raises:
            ToolNotFoundException: _description_

        Returns:
            dict[str, dict[str, Any]]: tools
        """
        tool_uids = [tool_instance.tool_id for tool_instance in tool_instances]
        tools: dict[str, dict[str, Any]] = self.tool_registry.get_available_tools(
            tool_uids
        )
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

            LogPublisher.publish(
                self.messaging_channel,
                LogPublisher.log_workflow(
                    "BUILD",
                    f"------ Building step {tool_instance.step}/{tool_uid}",
                    execution_id=execution_id,
                    organization_id=self.organization_id,
                ),
            )

            tool_envs = self.get_tool_environment_variables()
            logger.info(f"Tool Environments are collected for tool {tool_uid}")
            image_name = tool_instance.image_name
            image_tag = tool_instance.image_tag

            LogPublisher.publish(
                self.messaging_channel,
                LogPublisher.log_workflow(
                    "BUILD",
                    f"Building the tool {tool_uid} now...",
                    execution_id=execution_id,
                    organization_id=self.organization_id,
                ),
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
        file_execution_id: str,
        tool_sandbox: ToolSandbox,
    ) -> Any:
        return self.run_tool_with_retry(file_execution_id, tool_sandbox)

    def run_tool_with_retry(
        self,
        file_execution_id: str,
        tool_sandbox: ToolSandbox,
        max_retries: int = ToolExecution.MAXIMUM_RETRY,
    ) -> Any:
        error: dict[str, Any] | None = None
        for retry_count in range(max_retries):
            try:
                response = tool_sandbox.run_tool(file_execution_id, retry_count)
                if response:
                    return response
                logger.warning(
                    f"ToolExecutionException - Retrying "
                    f"({retry_count + 1}/{max_retries})"
                )
            except Exception as e:
                logger.warning(
                    f"Exception - Retrying ({retry_count + 1}/{max_retries}): "
                    f"{str(e)}"
                )

        logger.warning(f"Operation failed after {max_retries} retries, error: {error}")
        return None

    def get_tool_environment_variables(self) -> dict[str, Any]:
        """Obtain a dictionary of env variables required by a tool.

        This combines the user defined envs (coming from project_settings)
        as well as the env variables that are platform specific into
        one key-value store.

        Returns:
            dict[str, Any]: Dict of env variables for a tool
        """
        platform_vars = {
            ToolRV.PLATFORM_HOST: self.platform_service_host,
            ToolRV.PLATFORM_PORT: self.platform_service_port,
            ToolRV.PLATFORM_SERVICE_API_KEY: self.platform_service_api_key,
            ToolRV.PROMPT_HOST: self.prompt_host,
            ToolRV.PROMPT_PORT: self.prompt_port,
            ToolRV.X2TEXT_HOST: self.x2text_host,
            ToolRV.X2TEXT_PORT: self.x2text_port,
            ToolRV.EXECUTION_BY_TOOL: True,
            ToolRV.REDIS_HOST: self.redis_host,
            ToolRV.REDIS_PORT: self.redis_port,
            ToolRV.REDIS_USER: self.redis_user,
            ToolRV.REDIS_PASSWORD: self.redis_password,
        }
        # For async LLM Whisperer extraction
        if self.llmw_poll_interval:
            platform_vars[ToolRV.ADAPTER_LLMW_POLL_INTERVAL] = self.llmw_poll_interval
        if self.llmw_max_polls:
            platform_vars[ToolRV.ADAPTER_LLMW_MAX_POLLS] = self.llmw_max_polls
        if self.llmw_wait_timeout:
            platform_vars[ToolRV.ADAPTER_LLMW_WAIT_TIMEOUT] = self.llmw_wait_timeout
        return platform_vars

    @staticmethod
    def get_env(env_key: str, raise_exception: bool = False) -> str | None:
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
        if (env_value is None) and raise_exception:
            raise MissingEnvVariable(f"Env variable {env_key} is required")
        return env_value
