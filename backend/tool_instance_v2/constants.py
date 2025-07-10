class ToolInstanceKey:
    """Dict keys for ToolInstance model."""

    PK = "id"
    TOOL_ID = "tool_id"
    VERSION = "version"
    METADATA = "metadata"
    STEP = "step"
    STATUS = "status"
    WORKFLOW = "workflow"
    INPUT = "input"
    OUTPUT = "output"
    TI_COUNT = "tool_instance_count"


class JsonSchemaKey:
    """Dict Keys for Tool's Json schema."""

    TENANT_ID = "tenant_id"


class ToolInstanceErrors:
    TOOL_EXISTS = "Tool with this configuration already exists."
    DUPLICATE_API = "It appears that a duplicate call may have been made."


class ToolKey:
    """Dict keys for a Tool."""

    NAME = "name"
    DESCRIPTION = "description"
    ICON = "icon"
    FUNCTION_NAME = "function_name"
    OUTPUT_TYPE = "output_type"
    INPUT_TYPE = "input_type"
