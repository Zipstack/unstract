"""API Endpoint Constants

Internal API endpoint paths used by workers.
"""


class APIEndpoints:
    """Internal API endpoint paths."""

    # Workflow execution endpoints
    WORKFLOW_EXECUTION_STATUS = "/internal/workflow-execution/{execution_id}/status/"
    WORKFLOW_EXECUTION_DATA = "/internal/workflow-execution/{execution_id}/"
    WORKFLOW_FILE_EXECUTION_CREATE = "/internal/workflow-file-execution/create/"
    WORKFLOW_FILE_EXECUTION_STATUS = (
        "/internal/workflow-file-execution/{file_execution_id}/status/"
    )

    # Pipeline endpoints
    PIPELINE_STATUS = "/internal/pipeline/{pipeline_id}/status/"
    PIPELINE_LAST_RUN = "/internal/pipeline/{pipeline_id}/last-run/"

    # File history endpoints
    FILE_HISTORY_CREATE = "/internal/file-history/create/"
    FILE_HISTORY_CHECK_BATCH = "/internal/file-history/check-batch/"
    FILE_HISTORY_BY_WORKFLOW = "/internal/file-history/workflow/{workflow_id}/"

    # Workflow definition endpoints
    WORKFLOW_DEFINITION = "/internal/workflow/{workflow_id}/"
    WORKFLOW_SOURCE_CONFIG = "/internal/workflow/{workflow_id}/source-config/"
    WORKFLOW_DESTINATION_CONFIG = "/internal/workflow/{workflow_id}/destination-config/"

    # Notification endpoints
    WEBHOOK_SEND = "/internal/webhook/send/"
    NOTIFICATION_SEND = "/internal/notification/send/"

    # Health and monitoring endpoints
    WORKER_HEALTH = "/internal/worker/health/"
    WORKER_METRICS = "/internal/worker/metrics/"
