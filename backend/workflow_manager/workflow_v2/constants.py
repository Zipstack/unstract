class WorkflowKey:
    """Dict keys related to workflows."""

    LLM_RESPONSE = "llm_response"
    WF_STEPS = "steps"
    WF_TOOL = "tool"
    WF_INSTANCE_SETTINGS = "instance_settings"
    WF_TOOL_INSTANCE_ID = "tool_instance_id"
    WF_CONNECTOR_CLASS = "connector_class"
    WF_INPUT = "input"
    WF_OUTPUT = "output"
    WF_TOOL_UUID = "id"
    WF_ID = "workflow_id"
    WF_NAME = "workflow_name"
    WF_OWNER = "workflow_owner"
    WF_TOOL_INSTANCES = "tool_instances"
    WF_IS_ACTIVE = "is_active"
    EXECUTION_ACTION = "execution_action"
    # Keys from provisional workflow
    PWF_RESULT = "result"
    PWF_OUTPUT = "output"
    PWF_COST_TYPE = "cost_type"
    PWF_COST = "cost"
    PWF_TIME_TAKEN = "time_taken"
    WF_CACHE_PATTERN = r"^cache:{?\w{8}-?\w{4}-?\w{4}-?\w{4}-?\w{12}}?$"
    WF_PROJECT_GUID = "guid"


class WorkflowExecutionKey:
    WORKFLOW_EXECUTION_ID_PREFIX = "workflow"
    EXECUTION_ID = "execution_id"
    LOG_GUID = "log_guid"
    WITH_LOG = "with_log"


class WorkflowErrors:
    WORKFLOW_EXISTS = "Workflow with this configuration already exists."
    DUPLICATE_API = "It appears that a duplicate call may have been made."
    INVALID_EXECUTION_ID = "Invalid execution_id"


class CeleryConfigurations:
    INTERVAL = 2


class Tool:
    APIOPS = "apiops"


class WorkflowMessages:
    CACHE_CLEAR_SUCCESS = "Cache cleared successfully."
    CACHE_CLEAR_FAILED = "Failed to clear cache."
    CACHE_EMPTY = "Cache is already empty."
    CELERY_TIMEOUT_MESSAGE = (
        "Your request is being processed. Please wait."
        "You can check the status using the status API."
    )
    FILE_MARKER_CLEAR_SUCCESS = "File marker cleared successfully."
    FILE_MARKER_CLEAR_FAILED = "Failed to clear file marker."
    WORKFLOW_EXECUTION_NOT_FOUND = "Workflow execution not found."


class ResultKeys:
    METADATA = "metadata"
    CONFIDENCE_DATA = "confidence_data"
    OUTPUT = 'output'
