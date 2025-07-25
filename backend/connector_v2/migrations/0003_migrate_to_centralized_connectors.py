"""Migration to convert workflow-specific connectors to centralized connectors."""

import hashlib
import json
import logging
import uuid

from django.db import migrations

logger = logging.getLogger(__name__)


def migrate_to_centralized_connectors(apps, schema_editor):
    """Migrate existing workflow-specific connectors to centralized connectors.

    This migration:
    1. Finds all workflow-specific connectors
    2. Groups them by organization, connector ID, and connector metadata
    3. Marks first connector of each group as centralized
    4. Updates WorkflowEndpoint references to use the new centralized connectors
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")
    WorkflowEndpoint = apps.get_model("endpoint_v2", "WorkflowEndpoint")

    # Get all connector instances with select_related for performance
    connector_instances = ConnectorInstance.objects.select_related(
        "organization", "created_by", "modified_by"
    ).all()

    total_connectors = connector_instances.count()
    logger.info(f"Processing {total_connectors} connector instances for centralization")

    # Dictionary to store mapping from old redundant connectors to centralized connector
    connector_mapping = {}
    # Group connectors by organization and unique credential fingerprint
    connector_groups = {}
    # Set of connectors to delete
    connectors_to_delete_ids = set()

    # Group similar connectors to centralize one of them
    for connector in connector_instances:
        try:
            metadata_hash = None
            if connector.connector_metadata:
                metadata_json = json.dumps(connector.connector_metadata, sort_keys=True)
                metadata_hash = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()

            # Extract platform's connector name from "name|uuid" format
            connector_sys_name = (
                connector.connector_id.split("|")[0]
                if "|" in connector.connector_id
                else connector.connector_id
            )

            group_key = (
                connector.organization_id,
                connector_sys_name,
                metadata_hash,
            )

            if group_key not in connector_groups:
                connector_groups[group_key] = []
            connector_groups[group_key].append(connector)

        except Exception as e:
            logger.error(f"Error processing connector {connector.id}: {str(e)}")
            raise

    # Make centralized connectors for each group
    processed_groups = 0
    centralized_count = 0
    total_groups = len(connector_groups)

    for group_key, connectors in connector_groups.items():
        processed_groups += 1
        short_group_key = (
            group_key[0],
            group_key[1],
            group_key[2][:8] if group_key[2] else "None",
        )

        try:
            # Skip if only 1 connector present in a group
            if len(connectors) == 1:
                unique_connector = connectors[0]
                unique_connector.connector_name = (
                    f"{unique_connector.connector_name}-{uuid.uuid4().hex[:8]}"
                )
                logger.info(
                    f"[Group {processed_groups}/{total_groups}] {short_group_key}: "
                    f"Only 1 connector present, renaming to '{unique_connector.connector_name}'"
                )
                unique_connector.save()
                continue

            logger.info(
                f"[Group {processed_groups}/{total_groups}] {short_group_key}: "
                f"Found {len(connectors)} similar connectors to unify"
            )

            # First connector becomes the centralized one
            centralized_connector = connectors[0]
            original_name = centralized_connector.connector_name
            centralized_connector.connector_name = (
                f"{original_name}-{uuid.uuid4().hex[:8]}"
            )
            logger.info(
                f"[Group {processed_groups}/{total_groups}] {short_group_key}: "
                f"Centralizing '{original_name}' -> '{centralized_connector.connector_name}'"
            )
            centralized_connector.save()
            centralized_count += 1

            # Process each connector to be replaced
            for connector_to_delete in connectors[1:]:
                connector_mapping[connector_to_delete.id] = centralized_connector
                connectors_to_delete_ids.add(connector_to_delete.id)

        except Exception as e:
            logger.error(f"Error processing group {short_group_key}: {str(e)}")
            raise

    logger.info(
        f"Processed {processed_groups} connector groups, centralized {centralized_count}"
    )

    # Update WorkflowEndpoint references with bulk operations
    endpoint_updates = 0
    for old_connector_id, new_connector in connector_mapping.items():
        try:
            # Update all references in one query
            updated_count = WorkflowEndpoint.objects.filter(
                connector_instance_id=old_connector_id
            ).update(connector_instance=new_connector)

            if updated_count == 0:
                logger.debug(f"No WorkflowEndpoint uses connector '{old_connector_id}'")
                connectors_to_delete_ids.add(old_connector_id)
            else:
                endpoint_updates += updated_count
                logger.debug(
                    f"Updated {updated_count} endpoints for connector '{old_connector_id}'"
                )

        except Exception as e:
            logger.error(
                f"Error updating endpoints for connector {old_connector_id}: {str(e)}"
            )
            raise

    logger.info(f"Updated {endpoint_updates} WorkflowEndpoint references")

    # Bulk delete all processed connectors at once
    if connectors_to_delete_ids:
        try:
            delete_count = ConnectorInstance.objects.filter(
                id__in=connectors_to_delete_ids
            ).delete()[0]
            logger.info(f"Deleted {delete_count} redundant connectors")
        except Exception as e:
            logger.error(f"Error deleting redundant connectors: {str(e)}")
            raise

    logger.info(
        f"Migration completed: {centralized_count} centralized connectors created"
    )


def reverse_centralized_connectors(apps, schema_editor):
    """Reverse the migration by converting centralized connectors back to workflow-specific ones.

    This is a best-effort reversal that:
    1. Finds all centralized connectors
    2. For each WorkflowEndpoint using a centralized connector, creates a workflow-specific copy
    3. Updates the WorkflowEndpoint to use the workflow-specific copy
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")
    WorkflowEndpoint = apps.get_model("endpoint_v2", "WorkflowEndpoint")

    # Get all centralized connectors with prefetch for better performance
    centralized_connectors = ConnectorInstance.objects.prefetch_related(
        "workflow_endpoints"
    ).all()

    total_connectors = centralized_connectors.count()
    logger.info(f"Processing {total_connectors} centralized connectors for reversal")

    # Delete centralized connectors that are no longer referenced by any endpoints
    unused_connectors = []
    added_connector_count = 0
    processed_connectors = 0

    for centralized_connector in centralized_connectors:
        processed_connectors += 1

        try:
            # Get all endpoints using this centralized connector
            endpoints = WorkflowEndpoint.objects.filter(
                connector_instance=centralized_connector
            )

            if not endpoints.exists():
                logger.info(
                    f"[{processed_connectors}/{total_connectors}] Centralized connector "
                    f"'{centralized_connector}' has no endpoints, marking for deletion"
                )
                unused_connectors.append(centralized_connector.id)
                continue

            endpoint_ref_count = endpoints.count()
            logger.info(
                f"[{processed_connectors}/{total_connectors}] Centralized connector "
                f"'{centralized_connector}' has {endpoint_ref_count} endpoint(s) to process"
            )

            # Update connector instance for each endpoint except the last one
            # Last endpoint reuses the centralized connector itself
            for index, endpoint in enumerate(endpoints):
                workflow = endpoint.workflow
                endpoint_type = endpoint.endpoint_type

                connector_type = "INPUT" if endpoint_type == "SOURCE" else "OUTPUT"

                if index == endpoint_ref_count - 1:
                    # Last endpoint reuses the existing centralized connector
                    centralized_connector.workflow = workflow
                    centralized_connector.connector_type = connector_type
                    centralized_connector.save()
                    logger.debug(
                        f"Reused centralized connector for endpoint {endpoint.id}"
                    )
                else:
                    # Create new workflow-specific connector for other endpoints
                    endpoint_connector = ConnectorInstance.objects.create(
                        connector_name=centralized_connector.connector_name,
                        connector_id=centralized_connector.connector_id,
                        connector_metadata=centralized_connector.connector_metadata,
                        connector_version=centralized_connector.connector_version,
                        connector_type=connector_type,
                        connector_auth=centralized_connector.connector_auth,
                        connector_mode=centralized_connector.connector_mode,
                        workflow=workflow,
                        organization=centralized_connector.organization,
                        created_by=centralized_connector.created_by,
                        modified_by=centralized_connector.modified_by,
                    )
                    added_connector_count += 1
                    endpoint.connector_instance = endpoint_connector
                    endpoint.save()
                    logger.debug(f"Created new connector for endpoint {endpoint.id}")

        except Exception as e:
            logger.error(
                f"Error processing connector {centralized_connector.id}: {str(e)}"
            )
            raise

    # Delete unused centralized connectors
    if unused_connectors:
        try:
            delete_count = ConnectorInstance.objects.filter(
                id__in=unused_connectors
            ).delete()[0]
            logger.info(f"Deleted {delete_count} unused centralized connectors")
        except Exception as e:
            logger.error(f"Error deleting unused connectors: {str(e)}")
            raise
    else:
        logger.info("No unused centralized connectors to delete")

    logger.info(
        f"Reverse migration completed: added {added_connector_count} workflow-specific connectors"
    )


class Migration(migrations.Migration):
    dependencies = [
        (
            "connector_v2",
            "0002_alter_connectorinstance_connector_metadata_and_more",
        ),
        ("endpoint_v2", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            migrate_to_centralized_connectors, reverse_centralized_connectors
        ),
    ]
