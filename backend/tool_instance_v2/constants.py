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

    PROPERTIES = "properties"
    THEN = "then"
    INPUT_FILE_CONNECTOR = "inputFileConnector"
    OUTPUT_FILE_CONNECTOR = "outputFileConnector"
    OUTPUT_FOLDER = "outputFolder"
    ROOT_FOLDER = "rootFolder"
    TENANT_ID = "tenant_id"
    INPUT_DB_CONNECTOR = "inputDBConnector"
    OUTPUT_DB_CONNECTOR = "outputDBConnector"
    ENUM = "enum"
    PROJECT_DEFAULT = "Project Default"


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
