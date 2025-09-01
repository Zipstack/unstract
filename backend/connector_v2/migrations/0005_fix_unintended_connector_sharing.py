"""Migration to fix unintended connector sharing from centralization.

This migration addresses an issue where the centralization migration
(0003_migrate_to_centralized_connectors) inadvertently shared connectors
between users because it didn't include created_by in the grouping logic.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.db import migrations, transaction

logger = logging.getLogger(__name__)


def identify_problem_endpoints(apps) -> list[Any]:
    """Identify WorkflowEndpoint instances with incorrectly shared connectors.

    Returns endpoints where:
    - The connector's created_by != workflow's created_by
    - The connector is NOT explicitly shared with the workflow owner
    - The connector is NOT shared to the entire organization
    """
    WorkflowEndpoint = apps.get_model("endpoint_v2", "WorkflowEndpoint")

    problem_endpoints = []

    # Get all endpoints with their related data
    endpoints = (
        WorkflowEndpoint.objects.select_related(
            "workflow",
            "workflow__created_by",
            "connector_instance",
            "connector_instance__created_by",
        )
        .prefetch_related("connector_instance__shared_users")
        .all()
    )

    for endpoint in endpoints:
        if not endpoint.connector_instance:
            continue

        workflow = endpoint.workflow
        connector = endpoint.connector_instance

        # Skip if workflow or connector has no owner
        if not workflow.created_by or not connector.created_by:
            continue

        # Check if connector is owned by a different user
        if connector.created_by.id == workflow.created_by.id:
            continue

        # Check if connector is explicitly shared with workflow owner
        if workflow.created_by in connector.shared_users.all():
            continue

        # Check if connector is shared to entire org
        if connector.shared_to_org:
            continue

        # This is a problem case - connector is implicitly shared
        problem_endpoints.append(endpoint)
        logger.info(
            f"Found problem: Workflow '{workflow.workflow_name}' (owner: {workflow.created_by.email}) "
            f"uses connector '{connector.connector_name}' (owner: {connector.created_by.email}) "
            f"without explicit sharing"
        )

    return problem_endpoints


def duplicate_connector_for_user(
    connector: Any, user: Any, connector_instance_model: Any
) -> Any:
    """Create a duplicate of the connector for the specified user.

    Args:
        connector: The original connector to duplicate
        user: The user who should own the new connector
        connector_instance_model: The ConnectorInstance model class

    Returns:
        The newly created connector instance
    """
    # Create a new connector with the same settings but different owner
    new_connector = connector_instance_model.objects.create(
        connector_name=f"{connector.connector_name}-{uuid.uuid4().hex[:8]}",
        connector_id=connector.connector_id,
        connector_metadata=connector.connector_metadata,
        connector_version=connector.connector_version,
        connector_auth=connector.connector_auth,
        connector_mode=connector.connector_mode,
        organization=connector.organization,
        created_by=user,
        modified_by=user,
        shared_to_org=False,  # New connector is private to the user
    )

    logger.info(
        f"Created duplicate connector '{new_connector.connector_name}' "
        f"for user {user.email} (original: '{connector.connector_name}')"
    )

    return new_connector


def fix_unintended_sharing(apps, schema_editor):  # noqa: ARG001
    """Fix unintended connector sharing by creating user-specific copies.

    This migration:
    1. Identifies WorkflowEndpoints using connectors from other users without explicit sharing
    2. Creates duplicate connectors owned by the workflow owner
    3. Updates the WorkflowEndpoint to use the new connector
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")

    # Find all problem endpoints
    problem_endpoints = identify_problem_endpoints(apps)

    if not problem_endpoints:
        logger.info("No unintended connector sharing found. Migration complete.")
        return

    logger.info(
        f"Found {len(problem_endpoints)} endpoints with unintended connector sharing"
    )

    # Track connectors we've already duplicated for each user
    # Key: (original_connector_id, user_id), Value: new_connector
    duplicated_connectors = {}

    # Fix each problem endpoint
    fixed_count = 0
    with transaction.atomic():
        for endpoint in problem_endpoints:
            workflow = endpoint.workflow
            original_connector = endpoint.connector_instance
            workflow_owner = workflow.created_by

            # Check if we've already duplicated this connector for this user
            cache_key = (original_connector.id, workflow_owner.id)

            if cache_key in duplicated_connectors:
                # Reuse the already duplicated connector
                new_connector = duplicated_connectors[cache_key]
                logger.debug(
                    f"Reusing existing duplicate connector '{new_connector.connector_name}' "
                    f"for workflow '{workflow.workflow_name}'"
                )
            else:
                # Create a new duplicate
                new_connector = duplicate_connector_for_user(
                    original_connector, workflow_owner, ConnectorInstance
                )
                duplicated_connectors[cache_key] = new_connector

            # Update the endpoint to use the new connector
            endpoint.connector_instance = new_connector
            endpoint.save()
            fixed_count += 1

            logger.info(
                f"Updated workflow '{workflow.workflow_name}' endpoint to use "
                f"connector '{new_connector.connector_name}'"
            )

    logger.info(
        f"Migration completed: Fixed {fixed_count} endpoints, "
        f"created {len(duplicated_connectors)} new connectors"
    )


def reverse_fix_unintended_sharing(apps, schema_editor):  # noqa: ARG001
    """Reverse migration - cannot fully reverse as we've created new data.

    This logs a warning about manual cleanup that may be needed.
    The duplicated connectors will remain but won't cause issues.
    """
    logger.warning(
        "Reversing 0005_fix_unintended_connector_sharing migration. "
        "Note: Duplicated connectors created by the forward migration will remain. "
        "Manual cleanup may be required if you want to remove them. "
        "Original connectors and relationships are preserved."
    )

    # We could potentially:
    # 1. Find connectors with names ending in -[8 hex chars]
    # 2. Check if they're duplicates of other connectors
    # 3. Update endpoints back to original connectors
    # 4. Delete the duplicates
    #
    # However, this is risky as:
    # - Users may have modified the duplicated connectors
    # - The naming pattern might match legitimate connectors
    # - We'd need to ensure we're not breaking active workflows
    #
    # Therefore, we'll leave the reverse as a no-op with a warning


class Migration(migrations.Migration):
    dependencies = [
        (
            "connector_v2",
            "0004_remove_connectorinstance_unique_workflow_connector_and_more",
        ),
        ("endpoint_v2", "0001_initial"),
        ("workflow_v2", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            fix_unintended_sharing,
            reverse_fix_unintended_sharing,
        ),
    ]
