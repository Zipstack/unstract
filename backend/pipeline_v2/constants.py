from django.conf import settings


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


class PipelineScheduling:
    """Constants for pipeline scheduling configuration."""

    @classmethod
    def get_min_interval_seconds(cls) -> int:
        """Get minimum schedule interval in seconds from settings."""
        return settings.MIN_SCHEDULE_INTERVAL_SECONDS

    @classmethod
    def get_min_interval_minutes(cls) -> int:
        """Get minimum schedule interval in minutes from settings."""
        return cls.get_min_interval_seconds() // 60


class PipelineURL:
    """Constants for URL names."""

    DETAIL = "pipeline-detail"
    EXECUTIONS = "pipeline-executions"
    LIST = "pipeline-list"
    EXECUTE = "pipeline-execute"
    EXECUTE_NAMESPACE = "tenant:pipeline-execute"
