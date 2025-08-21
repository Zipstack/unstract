"""API Endpoint Constants

Internal API endpoint paths used by workers.
Configurable via environment variables for flexibility.
"""

from ..worker_patterns import build_internal_endpoint


class APIEndpoints:
    """Internal API endpoint paths."""

    # Workflow execution endpoints
    WORKFLOW_EXECUTION_STATUS = build_internal_endpoint(
        "workflow-execution/{execution_id}/status/"
    )
    WORKFLOW_EXECUTION_DATA = build_internal_endpoint(
        "workflow-execution/{execution_id}/"
    )
    WORKFLOW_FILE_EXECUTION_CREATE = build_internal_endpoint(
        "workflow-file-execution/create/"
    )
    WORKFLOW_FILE_EXECUTION_STATUS = build_internal_endpoint(
        "workflow-file-execution/{file_execution_id}/status/"
    )

    # Pipeline endpoints
    PIPELINE_STATUS = build_internal_endpoint("pipeline/{pipeline_id}/status/")
    PIPELINE_LAST_RUN = build_internal_endpoint("pipeline/{pipeline_id}/last-run/")

    # File history endpoints
    FILE_HISTORY_CREATE = build_internal_endpoint("file-history/create/")
    FILE_HISTORY_CHECK_BATCH = build_internal_endpoint("file-history/check-batch/")
    FILE_HISTORY_BY_WORKFLOW = build_internal_endpoint(
        "file-history/workflow/{workflow_id}/"
    )

    # Workflow definition endpoints
    WORKFLOW_DEFINITION = build_internal_endpoint("workflow/{workflow_id}/")
    WORKFLOW_SOURCE_CONFIG = build_internal_endpoint(
        "workflow/{workflow_id}/source-config/"
    )
    WORKFLOW_DESTINATION_CONFIG = build_internal_endpoint(
        "workflow/{workflow_id}/destination-config/"
    )

    # Notification endpoints
    WEBHOOK_SEND = build_internal_endpoint("webhook/send/")
    NOTIFICATION_SEND = build_internal_endpoint("notification/send/")

    # Health and monitoring endpoints
    WORKER_HEALTH = build_internal_endpoint("worker/health/")
    WORKER_METRICS = build_internal_endpoint("worker/metrics/")
