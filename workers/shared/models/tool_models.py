"""Tool Configuration Data Models

This module provides strongly-typed dataclasses for tool configurations,
replacing fragile dictionary-based tool handling with type-safe structures.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolInstanceConfig:
    """Strongly-typed configuration for tool instances.

    Replaces dictionary-based tool configuration with type-safe structure
    that provides validation, autocomplete, and clear documentation.
    """

    tool_id: str
    tool_name: str
    tool_settings: dict[str, Any] = field(default_factory=dict)
    step_name: str = ""
    prompt_registry_id: str | None = None
    enable: bool = True
    step: int | None = None
    tool_version: str | None = None
    tool_description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    def __post_init__(self):
        """Validate tool configuration after initialization."""
        if not self.tool_id:
            raise ValueError("tool_id is required for tool configuration")

        if not self.tool_name:
            raise ValueError("tool_name is required for tool configuration")

        # Ensure tool_settings is a dictionary
        if not isinstance(self.tool_settings, dict):
            raise ValueError("tool_settings must be a dictionary")

    @property
    def is_enabled(self) -> bool:
        """Check if the tool is enabled."""
        return self.enable

    @property
    def has_prompt_registry(self) -> bool:
        """Check if the tool has a prompt registry."""
        return bool(self.prompt_registry_id)

    @property
    def has_settings(self) -> bool:
        """Check if the tool has any settings."""
        return bool(self.tool_settings)

    def get_setting(self, setting_key: str, default: Any = None) -> Any:
        """Get a tool setting value."""
        return self.tool_settings.get(setting_key, default)

    def set_setting(self, setting_key: str, value: Any) -> None:
        """Set a tool setting value."""
        self.tool_settings[setting_key] = value

    def update_settings(self, settings: dict[str, Any]) -> None:
        """Update multiple tool settings."""
        self.tool_settings.update(settings)

    def to_dict(self) -> dict[str, Any]:
        """Convert tool configuration to dictionary for serialization."""
        result = {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "settings": self.tool_settings,
            "step_name": self.step_name,
            "enable": self.enable,
        }

        if self.prompt_registry_id:
            result["prompt_registry_id"] = self.prompt_registry_id

        if self.step is not None:
            result["step"] = self.step

        if self.tool_version:
            result["tool_version"] = self.tool_version

        if self.tool_description:
            result["tool_description"] = self.tool_description

        if self.input_schema:
            result["input_schema"] = self.input_schema

        if self.output_schema:
            result["output_schema"] = self.output_schema

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolInstanceConfig":
        """Create ToolInstanceConfig from dictionary data.

        Args:
            data: Dictionary containing tool configuration data

        Returns:
            ToolInstanceConfig instance
        """
        return cls(
            tool_id=data["tool_id"],
            tool_name=data.get("tool_name", ""),
            tool_settings=data.get("settings", {}),
            step_name=data.get("step_name", ""),
            prompt_registry_id=data.get("prompt_registry_id"),
            enable=data.get("enable", True),
            step=data.get("step"),
            tool_version=data.get("tool_version"),
            tool_description=data.get("tool_description"),
            input_schema=data.get("input_schema"),
            output_schema=data.get("output_schema"),
        )


@dataclass
class ToolExecutionRequest:
    """Strongly-typed request for tool execution."""

    tool_instance_id: str
    input_data: dict[str, Any]
    file_data: dict[str, Any] | None = None
    execution_context: dict[str, Any] | None = None
    organization_id: str | None = None
    timeout: int | None = None

    def __post_init__(self):
        """Validate execution request after initialization."""
        if not self.tool_instance_id:
            raise ValueError("tool_instance_id is required for tool execution")

        if not isinstance(self.input_data, dict):
            raise ValueError("input_data must be a dictionary")

    def to_dict(self) -> dict[str, Any]:
        """Convert execution request to dictionary for API calls."""
        result = {
            "input_data": self.input_data,
            "file_data": self.file_data or {},
            "execution_context": self.execution_context or {},
        }

        if self.organization_id:
            result["organization_id"] = self.organization_id

        if self.timeout:
            result["timeout"] = self.timeout

        return result


@dataclass
class ToolExecutionResult:
    """Strongly-typed result from tool execution."""

    execution_id: str
    tool_instance_id: str
    status: str
    output_data: dict[str, Any] | None = None
    execution_time: float | None = None
    error_message: str | None = None
    step_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        """Validate execution result after initialization."""
        if not self.execution_id:
            raise ValueError("execution_id is required for tool execution result")

        if not self.tool_instance_id:
            raise ValueError("tool_instance_id is required for tool execution result")

        if not self.status:
            raise ValueError("status is required for tool execution result")

    @property
    def is_successful(self) -> bool:
        """Check if tool execution was successful."""
        return self.status == "COMPLETED" and not self.error_message

    @property
    def is_failed(self) -> bool:
        """Check if tool execution failed."""
        return self.status == "ERROR" or bool(self.error_message)

    @property
    def has_output(self) -> bool:
        """Check if tool execution produced output."""
        return bool(self.output_data)

    def get_output_field(self, field_name: str, default: Any = None) -> Any:
        """Get a field from the output data."""
        if not self.output_data:
            return default
        return self.output_data.get(field_name, default)

    def to_dict(self) -> dict[str, Any]:
        """Convert execution result to dictionary for serialization."""
        result = {
            "execution_id": self.execution_id,
            "tool_instance_id": self.tool_instance_id,
            "status": self.status,
        }

        if self.output_data:
            result["output_data"] = self.output_data

        if self.execution_time is not None:
            result["execution_time"] = self.execution_time

        if self.error_message:
            result["error_message"] = self.error_message

        if self.step_results:
            result["step_results"] = self.step_results

        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolExecutionResult":
        """Create ToolExecutionResult from dictionary data."""
        return cls(
            execution_id=data["execution_id"],
            tool_instance_id=data["tool_instance_id"],
            status=data["status"],
            output_data=data.get("output_data"),
            execution_time=data.get("execution_time"),
            error_message=data.get("error_message"),
            step_results=data.get("step_results", []),
            metadata=data.get("metadata"),
        )


@dataclass
class WorkflowToolsConfig:
    """Strongly-typed configuration for workflow tools.

    Contains the complete set of tool configurations for a workflow
    with validation and management methods.
    """

    tools: list[ToolInstanceConfig] = field(default_factory=list)
    workflow_id: str | None = None
    execution_id: str | None = None

    def __post_init__(self):
        """Validate workflow tools configuration."""
        if not isinstance(self.tools, list):
            raise ValueError("tools must be a list of ToolInstanceConfig instances")

        for i, tool in enumerate(self.tools):
            if not isinstance(tool, ToolInstanceConfig):
                raise ValueError(
                    f"Tool at index {i} must be a ToolInstanceConfig instance"
                )

    @property
    def tool_count(self) -> int:
        """Get the number of tools in the workflow."""
        return len(self.tools)

    @property
    def enabled_tools(self) -> list[ToolInstanceConfig]:
        """Get only the enabled tools."""
        return [tool for tool in self.tools if tool.is_enabled]

    @property
    def enabled_tool_count(self) -> int:
        """Get the number of enabled tools."""
        return len(self.enabled_tools)

    def get_tool_by_id(self, tool_id: str) -> ToolInstanceConfig | None:
        """Get a tool by its ID."""
        for tool in self.tools:
            if tool.tool_id == tool_id:
                return tool
        return None

    def get_tool_by_name(self, tool_name: str) -> ToolInstanceConfig | None:
        """Get a tool by its name."""
        for tool in self.tools:
            if tool.tool_name == tool_name:
                return tool
        return None

    def get_tools_by_step(self) -> list[ToolInstanceConfig]:
        """Get tools sorted by step number."""
        return sorted(
            [tool for tool in self.tools if tool.step is not None],
            key=lambda t: t.step or 0,
        )

    def add_tool(self, tool: ToolInstanceConfig) -> None:
        """Add a tool to the workflow."""
        if not isinstance(tool, ToolInstanceConfig):
            raise ValueError("Tool must be a ToolInstanceConfig instance")
        self.tools.append(tool)

    def remove_tool(self, tool_id: str) -> bool:
        """Remove a tool from the workflow by ID."""
        for i, tool in enumerate(self.tools):
            if tool.tool_id == tool_id:
                del self.tools[i]
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert workflow tools configuration to dictionary."""
        return {
            "tools": [tool.to_dict() for tool in self.tools],
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowToolsConfig":
        """Create WorkflowToolsConfig from dictionary data."""
        tools_data = data.get("tools", [])
        tools = [ToolInstanceConfig.from_dict(tool_data) for tool_data in tools_data]

        return cls(
            tools=tools,
            workflow_id=data.get("workflow_id"),
            execution_id=data.get("execution_id"),
        )


# Utility functions for tool configuration conversion
def convert_tools_config_from_dict(
    tools_config: list[dict[str, Any]],
) -> list[ToolInstanceConfig]:
    """Convert list of tool configuration dictionaries to ToolInstanceConfig list.

    Args:
        tools_config: List of tool configuration dictionaries

    Returns:
        List of ToolInstanceConfig instances
    """
    return [ToolInstanceConfig.from_dict(tool_config) for tool_config in tools_config]


def convert_tools_config_to_dict(tools: list[ToolInstanceConfig]) -> list[dict[str, Any]]:
    """Convert list of ToolInstanceConfig to dictionary list.

    Args:
        tools: List of ToolInstanceConfig instances

    Returns:
        List of tool configuration dictionaries
    """
    return [tool.to_dict() for tool in tools]
