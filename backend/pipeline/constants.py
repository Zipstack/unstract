class PipelineConstants:
    """Constants for Pipelines."""

    TYPE = "type"
    ETL_PIPELINE = "ETL"
    TASK_PIPELINE = "TASK"
    ETL = "etl"
    TASK = "task"
    CREATE_ACTION = "create"
    UPDATE_ACTION = "update"
    PIPELINE_GUID = "id"
    ACTION = "action"
    NOT_CONFIGURED = "Connector not configured."
    SOURCE_NOT_CONFIGURED = "Source not configured."
    DESTINATION_NOT_CONFIGURED = "Destination not configured."
    SOURCE_ICON = "source_icon"
    DESTINATION_ICON = "destination_icon"
    SOURCE_NAME = "source_name"
    DESTINATION_NAME = "destination_name"
    INPUT_FILE = "input_file_connector"
    INPUT_DB = "input_db_connector"
    OUTPUT_FILE = "output_file_connector"
    OUTPUT_DB = "output_db_connector"
    SOURCE = "source"
    DEST = "dest"


class PipelineExecutionKey:
    PIPELINE = "pipeline"
    EXECUTION = "execution"


class PipelineKey:
    """Constants for the Pipeline model."""

    PIPELINE_GUID = "id"
    PIPELINE_NAME = "pipeline_name"
    WORKFLOW = "workflow"
    APP_ID = "app_id"
    ACTIVE = "active"
    SCHEDULED = "scheduled"
    PIPELINE_TYPE = "pipeline_type"
    RUN_COUNT = "run_count"
    LAST_RUN_TIME = "last_run_time"
    LAST_RUN_STATUS = "last_run_status"
    # Used by serializer
    CRON_DATA = "cron_data"
    WORKFLOW_NAME = "workflow_name"
    WORKFLOW_ID = "workflow_id"
    CRON_STRING = "cron_string"
    PIPELINE_ID = "pipeline_id"


class PipelineErrors:
    PIPELINE_EXISTS = "Pipeline with this configuration might already exist or some mandatory field is missing."  # noqa: E501
    DUPLICATE_API = "It appears that a duplicate call may have been made."
    INVALID_WF = "The provided workflow does not exist"


class PipelineURL:
    """Constants for URL names."""

    DETAIL = "pipeline-detail"
    LIST = "pipeline-list"
    EXECUTE = "pipeline-execute"
