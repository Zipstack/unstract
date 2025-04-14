from typing import Any

from unstract.tool_sandbox.constants import ToolCommandKey, UnstractRunner
from unstract.tool_sandbox.helper import ToolSandboxHelper


class ToolSandbox:
    def __init__(
        self,
        tool_guid: str,
        image_name: str,
        image_tag: str,
        organization_id: str = "",
        workflow_id: str = "",
        execution_id: str = "",
        tool_instance_id: str | None = None,
        environment_variables: dict[str, Any] = {},
        messaging_channel: str | None = None,
    ):
        """PLATFORM_SERVICE_API_KEY should be available in the environment."""
        self.messaging_channel = str(messaging_channel)
        self.helper = ToolSandboxHelper(
            organization_id=organization_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            messaging_channel=self.messaging_channel,
            environment_variables=environment_variables,
        )
        self.tool_guid = tool_guid
        self.tool_instance_id = tool_instance_id
        self.image_name = image_name
        self.image_tag = image_tag
        self.settings: dict[str, Any] = {}

    def set_tool_instance_settings(self, tool_settings: dict[str, Any]) -> None:
        self.settings = tool_settings

    def get_tool_uid(self) -> str:
        return self.tool_guid

    def get_tool_instance_id(self) -> str | None:
        if self.tool_instance_id:
            # make sure to return str instead of UUId
            return str(self.tool_instance_id)
        return None

    def get_tool_instance_settings(self) -> dict[str, Any]:
        return self.settings

    def get_spec(self) -> dict[str, Any] | None:
        spec = self.helper.make_get_request(
            self.image_name, self.image_tag, UnstractRunner.SPEC_API_ENDPOINT
        )
        if not spec:
            return None
        result: dict[str, Any] | None = self.helper.convert_str_to_dict(
            spec.get(ToolCommandKey.SPEC)
        )
        return result

    def get_properties(self) -> dict[str, Any] | None:
        properties = self.helper.make_get_request(
            self.image_name,
            self.image_tag,
            UnstractRunner.PROPERTIES_API_ENDPOINT,
        )
        if not properties:
            return None
        result: dict[str, Any] | None = self.helper.convert_str_to_dict(
            properties.get(ToolCommandKey.PROPERTIES)
        )
        return result

    def get_icon(self) -> str | None:
        icon = self.helper.make_get_request(
            self.image_name, self.image_tag, UnstractRunner.ICON_API_ENDPOINT
        )
        if not icon:
            return None
        result: str | None = icon.get(ToolCommandKey.ICON)
        return result

    def get_variables(self) -> dict[str, Any] | None:
        variables = self.helper.make_get_request(
            self.image_name,
            self.image_tag,
            UnstractRunner.VARIABLES_API_ENDPOINT,
        )
        if not variables:
            return None
        result: dict[str, Any] | None = self.helper.convert_str_to_dict(
            variables.get(ToolCommandKey.VARIABLES)
        )
        return result

    def run_tool(
        self, file_execution_id: str, retry_count: int | None = None
    ) -> dict[str, Any] | None:
        return self.helper.call_tool_handler(  # type: ignore
            file_execution_id,
            self.image_name,
            self.image_tag,
            self.settings,
            retry_count,
        )
