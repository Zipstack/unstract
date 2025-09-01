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
from django.db.models import Exists, F, OuterRef, Q

logger = logging.getLogger(__name__)


def identify_problem_endpoints(apps, db_alias: str) -> list[Any]:
    """Identify WorkflowEndpoint instances with incorrectly shared connectors.

    Returns endpoints where:
    - The connector's created_by != workflow's created_by
    - The connector is NOT explicitly shared with the workflow owner
    - The connector is NOT shared to the entire organization

    Args:
        apps: Django apps registry from migration context
        db_alias: Database alias for multi-database routing
    """
    WorkflowEndpoint = apps.get_model("endpoint_v2", "WorkflowEndpoint")
    User = apps.get_model("account_v2", "User")

    # Create a subquery to check if the workflow owner is in the connector's shared_users
    shared_with_workflow_owner = User.objects.using(db_alias).filter(
        shared_connectors=OuterRef("connector_instance"),
        id=OuterRef("workflow__created_by"),
    )

    # Build the main query with database-level filtering
    problem_endpoints = list(
        WorkflowEndpoint.objects.using(db_alias)
        .select_related(
            "workflow",
            "workflow__created_by",
            "connector_instance",
            "connector_instance__created_by",
        )
        # Exclude endpoints with no connector instance
        .exclude(connector_instance__isnull=True)
        # Exclude if workflow or connector has no owner
        .exclude(
            Q(workflow__created_by__isnull=True)
            | Q(connector_instance__created_by__isnull=True)
        )
        # Exclude if same owner (connector owned by workflow owner)
        .exclude(workflow__created_by=F("connector_instance__created_by"))
        # Exclude if connector is shared to entire org
        .exclude(connector_instance__shared_to_org=True)
        # Exclude if connector is explicitly shared with workflow owner
        .exclude(Exists(shared_with_workflow_owner))
    )

    # Log the found problems for debugging
    for endpoint in problem_endpoints:
        workflow = endpoint.workflow
        connector = endpoint.connector_instance
        logger.info(
            "Found problem: workflow_id=%s (owner_id=%s) endpoint_id=%s uses connector_id=%s (owner_id=%s) without explicit sharing",
            workflow.id,
            workflow.created_by_id,
            endpoint.id,
            connector.id,
            connector.created_by_id,
        )

    return problem_endpoints


def duplicate_connector_for_user(
    connector: Any, user: Any, connector_instance_model: Any, db_alias: str
) -> Any:
    """Create a duplicate of the connector for the specified user.

    Args:
        connector: The original connector to duplicate
        user: The user who should own the new connector
        connector_instance_model: The ConnectorInstance model class
        db_alias: Database alias for multi-database routing

    Returns:
        The newly created connector instance
    """
    # Create a new connector with the same settings but different owner
    new_connector = connector_instance_model.objects.using(db_alias).create(
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


def fix_unintended_sharing(apps, schema_editor):
    """Fix unintended connector sharing by creating user-specific copies.

    This migration:
    1. Identifies WorkflowEndpoints using connectors from other users without explicit sharing
    2. Creates duplicate connectors owned by the workflow owner
    3. Updates the WorkflowEndpoint to use the new connector
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")
    db_alias = schema_editor.connection.alias

    # Find all problem endpoints
    problem_endpoints = identify_problem_endpoints(apps, db_alias)

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
    with transaction.atomic(using=db_alias):
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
                    original_connector, workflow_owner, ConnectorInstance, db_alias
                )
                duplicated_connectors[cache_key] = new_connector

            # Update the endpoint to use the new connector
            endpoint.connector_instance = new_connector
            endpoint.save(using=db_alias)
            fixed_count += 1

            logger.info(
                "Updated endpoint_id=%s for workflow_id=%s to connector_id=%s",
                endpoint.id,
                workflow.id,
                new_connector.id,
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
