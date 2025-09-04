"""Base Internal API Endpoints Configuration

Centralized configuration for internal service-to-service API endpoints.
This module provides base endpoint definitions that are shared between
OSS and cloud deployments to avoid duplication.

This file serves as the single source of truth for all base internal
API endpoints. Cloud/enterprise versions import from this file to
maintain consistency and avoid duplication.
"""

from .internal_api_constants import build_internal_endpoint


def get_base_internal_api_endpoints() -> dict[str, str]:
    """Get base internal API endpoints that are common to all deployments.

    This centralizes the base endpoint definitions to avoid duplication
    between OSS and cloud versions. All core internal API endpoints
    should be defined here.

    Returns:
        Dictionary mapping endpoint names to URL patterns
    """
    return {
        # Health & Utilities
        "health": build_internal_endpoint("health/"),
        # Workflow Execution APIs (workflow_manager app)
        "workflow_execution": build_internal_endpoint("workflow/"),
        "workflow_execution_detail": build_internal_endpoint("workflow/{id}/"),
        "workflow_execution_status": build_internal_endpoint("workflow/{id}/status/"),
        "file_batch_create": build_internal_endpoint("workflow/file-batch/"),
        "file_execution": build_internal_endpoint("file-execution/"),
        "file_execution_status": build_internal_endpoint("file-execution/{id}/status/"),
        # Tool Execution APIs (tool_instance_v2 app)
        "tool_execution": build_internal_endpoint("tool-execution/"),
        "tool_execution_execute": build_internal_endpoint("tool-execution/{id}/execute/"),
        "tool_execution_status": build_internal_endpoint(
            "tool-execution/status/{execution_id}/"
        ),
        "tool_instances_by_workflow": build_internal_endpoint(
            "tool-execution/workflow/{workflow_id}/instances/"
        ),
        # File History APIs (workflow_manager.workflow_v2 app)
        "file_history_by_cache_key": build_internal_endpoint(
            "file-history/cache-key/{cache_key}/"
        ),
        "file_history_create": build_internal_endpoint("file-history/create/"),
        "file_history_status": build_internal_endpoint(
            "file-history/status/{file_history_id}/"
        ),
        # Execution Finalization APIs (workflow_manager.execution app)
        "execution_finalize": build_internal_endpoint(
            "execution/finalize/{execution_id}/"
        ),
        "execution_cleanup": build_internal_endpoint("execution/cleanup/"),
        "execution_finalization_status": build_internal_endpoint(
            "execution/finalization-status/{execution_id}/"
        ),
        # Webhook APIs (notification_v2 app)
        "webhook_config": build_internal_endpoint("webhook/"),
        "webhook_send": build_internal_endpoint("webhook/send/"),
        "webhook_batch": build_internal_endpoint("webhook/batch/"),
        "webhook_test": build_internal_endpoint("webhook/test/"),
        "webhook_status": build_internal_endpoint("webhook/status/{task_id}/"),
        # Organization Context (account_v2 app)
        "organization": build_internal_endpoint("organization/{org_id}/"),
        # Platform Settings APIs
        "platform_key": build_internal_endpoint("platform-settings/platform-key/"),
        # Configuration APIs (configuration app)
        "configuration": build_internal_endpoint("configuration/{config_key}/"),
    }


# Convenience alias for backward compatibility
get_base_endpoints = get_base_internal_api_endpoints
