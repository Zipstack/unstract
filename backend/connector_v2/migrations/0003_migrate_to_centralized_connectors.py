"""Migration to convert workflow-specific connectors to centralized connectors."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

from django.db import migrations

logger = logging.getLogger(__name__)


def _compute_metadata_hash(connector_metadata: dict[str, Any] | None) -> str | None:
    """Compute SHA256 hash of connector metadata."""
    if not connector_metadata:
        return None
    metadata_json = json.dumps(connector_metadata, sort_keys=True)
    return hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()


def _extract_connector_sys_name(connector_id: str) -> str:
    """Extract platform's connector name from 'name|uuid' format."""
    if "|" in connector_id:
        return connector_id.split("|")[0]
    return connector_id


def _get_short_group_key(group_key: tuple[Any, str, str | None]) -> tuple[Any, str, str]:
    """Generate a shortened group key for logging."""
    return (
        group_key[0],
        group_key[1],
        group_key[2][:8] if group_key[2] else "None",
    )


def _group_connectors(
    connector_instances: Any,
) -> dict[tuple[Any, str, str | None], list[Any]]:
    """Group connectors by organization, connector type, and metadata hash."""
    connector_groups = {}
    skipped_connectors = 0

    for connector in connector_instances:
        try:
            # Try to access connector_metadata - this may fail due to encryption key mismatch
            try:
                metadata_hash = _compute_metadata_hash(connector.connector_metadata)
            except Exception as decrypt_error:
                # Log the encryption error and skip this connector
                logger.warning(
                    f"Skipping connector {connector.id} due to encryption error: {str(decrypt_error)}. "
                    f"This is likely due to a changed ENCRYPTION_KEY."
                )
                skipped_connectors += 1
                continue

            connector_sys_name = _extract_connector_sys_name(connector.connector_id)

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

    if skipped_connectors > 0:
        logger.warning(
            f"Skipped {skipped_connectors} connectors due to encryption key issues"
        )

    return connector_groups


def _process_single_connector(
    connector: Any,
    processed_groups: int,
    total_groups: int,
    short_group_key: tuple[Any, str, str],
    connector_instance_model: Any,
) -> None:
    """Process a group with only one connector."""
    base_name = connector.connector_name
    new_name = f"{base_name}-{uuid.uuid4().hex[:8]}"

    # For performance with large datasets, UUID collisions are extremely rare
    # If uniqueness becomes critical, we can add collision detection later

    connector.connector_name = new_name
    logger.info(
        f"[Group {processed_groups}/{total_groups}] {short_group_key}: "
        f"Only 1 connector present, renaming to '{connector.connector_name}'"
    )
    connector.save()


def _centralize_connector_group(
    connectors: list[Any],
    processed_groups: int,
    total_groups: int,
    short_group_key: tuple[Any, str, str],
    connector_instance_model: Any,
) -> tuple[Any, dict[Any, Any], set[Any]]:
    """Centralize a group of multiple connectors."""
    logger.info(
        f"[Group {processed_groups}/{total_groups}] {short_group_key}: "
        f"Found {len(connectors)} similar connectors to unify"
    )

    # First connector becomes the centralized one
    centralized_connector = connectors[0]
    original_name = centralized_connector.connector_name
    new_name = f"{original_name}-{uuid.uuid4().hex[:8]}"

    # For performance with large datasets, UUID collisions are extremely rare
    # If uniqueness becomes critical, we can add collision detection later

    centralized_connector.connector_name = new_name

    logger.info(
        f"[Group {processed_groups}/{total_groups}] {short_group_key}: "
        f"Centralizing '{original_name}' -> '{centralized_connector.connector_name}'"
    )
    centralized_connector.save()

    # Build mapping for connectors to be replaced
    connector_mapping = {}
    connectors_to_delete = set()

    for connector_to_delete in connectors[1:]:
        connector_mapping[connector_to_delete.id] = centralized_connector
        connectors_to_delete.add(connector_to_delete.id)

    return centralized_connector, connector_mapping, connectors_to_delete


def _update_workflow_endpoints(
    connector_mapping: dict[Any, Any], workflow_endpoint_model: Any
) -> tuple[int, set[Any]]:
    """Update WorkflowEndpoint references to use centralized connectors."""
    endpoint_updates = 0
    connectors_to_delete = set()

    for old_connector_id, new_connector in connector_mapping.items():
        try:
            updated_count = workflow_endpoint_model.objects.filter(
                connector_instance_id=old_connector_id
            ).update(connector_instance=new_connector)

            if updated_count == 0:
                logger.debug(f"No WorkflowEndpoint uses connector '{old_connector_id}'")
                connectors_to_delete.add(old_connector_id)
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
    return endpoint_updates, connectors_to_delete


def _delete_redundant_connectors(
    connectors_to_delete_ids: set[Any], connector_instance_model: Any
) -> int:
    """Delete redundant connectors in bulk."""
    if not connectors_to_delete_ids:
        return 0

    try:
        delete_count = connector_instance_model.objects.filter(
            id__in=connectors_to_delete_ids
        ).delete()[0]
        logger.info(f"Deleted {delete_count} redundant connectors")
        return delete_count
    except Exception as e:
        logger.error(f"Error deleting redundant connectors: {str(e)}")
        raise


def _fix_remaining_duplicate_names(connector_instance_model: Any) -> int:
    """Fix any remaining duplicate connector names within organizations."""
    from django.db.models import Count

    # Find all organizations with duplicate connector names (optimized query)
    duplicates = list(
        connector_instance_model.objects.values("connector_name", "organization_id")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .order_by("organization_id", "connector_name")
    )

    total_duplicates = len(duplicates)
    if total_duplicates == 0:
        logger.info("No duplicate connector names found after migration")
        return 0

    logger.info(
        f"Found {total_duplicates} groups with duplicate connector names - fixing"
    )
    fixed_count = 0

    # Process in batches to avoid memory issues
    batch_size = 20
    for i in range(0, len(duplicates), batch_size):
        batch = duplicates[i : i + batch_size]
        logger.info(
            f"Processing batch {i//batch_size + 1}/{(len(duplicates)-1)//batch_size + 1}"
        )

        for dup_info in batch:
            connector_name = dup_info["connector_name"]
            org_id = dup_info["organization_id"]

            # Get all connectors with this name in this organization (select only needed fields)
            duplicate_connectors = list(
                connector_instance_model.objects.filter(
                    connector_name=connector_name, organization_id=org_id
                )
                .only("id", "connector_name", "organization_id")
                .order_by("id")
            )

            if len(duplicate_connectors) <= 1:
                continue  # Skip if no longer duplicates

            # Prepare batch updates (keep first, rename others)
            updates = []
            existing_names_in_org = set(
                connector_instance_model.objects.filter(
                    organization_id=org_id
                ).values_list("connector_name", flat=True)
            )

            for j, connector in enumerate(duplicate_connectors[1:], 1):  # Skip first
                base_name = connector_name
                new_name = f"{base_name}-{uuid.uuid4().hex[:8]}"

                # Simple collision check against existing names in this org
                attempt = 0
                while new_name in existing_names_in_org and attempt < 5:
                    new_name = f"{base_name}-{uuid.uuid4().hex[:8]}"
                    attempt += 1

                existing_names_in_org.add(new_name)  # Track new names
                connector.connector_name = new_name
                updates.append(connector)
                fixed_count += 1

            # Bulk update for better performance
            if updates:
                connector_instance_model.objects.bulk_update(
                    updates, ["connector_name"], batch_size=100
                )
                logger.info(
                    f"  Fixed {len(updates)} duplicates of '{connector_name}' in org {org_id}"
                )

    logger.info(f"Fixed {fixed_count} duplicate connector names")
    return fixed_count


def migrate_to_centralized_connectors(apps, schema_editor):  # noqa: ARG001
    """Migrate existing workflow-specific connectors to centralized connectors.

    This migration:
    1. Finds all workflow-specific connectors
    2. Groups them by organization, connector ID, and connector metadata
    3. Marks first connector of each group as centralized
    4. Updates WorkflowEndpoint references to use the new centralized connectors
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")  # NOSONAR
    WorkflowEndpoint = apps.get_model("endpoint_v2", "WorkflowEndpoint")  # NOSONAR

    # Get all connector instances, but defer the encrypted metadata field to avoid
    # automatic decryption failures when the encryption key has changed
    connector_instances = (
        ConnectorInstance.objects.select_related(
            "organization", "created_by", "modified_by"
        )
        .defer("connector_metadata")
        .all()
    )

    total_connectors = connector_instances.count()
    logger.info(f"Processing {total_connectors} connector instances for centralization")

    # Group connectors by organization and unique credential fingerprint
    connector_groups = _group_connectors(connector_instances)

    # Safety check: If we have connectors but all were skipped, this indicates a serious issue
    if total_connectors > 0 and len(connector_groups) == 0:
        error_msg = (
            f"CRITICAL: All {total_connectors} connectors were skipped due to encryption errors. "
            f"This likely means the ENCRYPTION_KEY has changed. Please restore the correct "
            f"ENCRYPTION_KEY and retry the migration. The migration has been aborted to prevent "
            f"data loss."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # Process each group and centralize connectors
    processed_groups = 0
    centralized_count = 0
    total_groups = len(connector_groups)
    all_connector_mappings = {}
    all_connectors_to_delete = set()

    for group_key, connectors in connector_groups.items():
        processed_groups += 1
        short_group_key = _get_short_group_key(group_key)

        try:
            # Process single connector groups differently
            if len(connectors) == 1:
                _process_single_connector(
                    connectors[0],
                    processed_groups,
                    total_groups,
                    short_group_key,
                    ConnectorInstance,
                )
                continue

            # Centralize multiple connectors
            _, connector_mapping, connectors_to_delete = _centralize_connector_group(
                connectors,
                processed_groups,
                total_groups,
                short_group_key,
                ConnectorInstance,
            )

            centralized_count += 1
            all_connector_mappings.update(connector_mapping)
            all_connectors_to_delete.update(connectors_to_delete)

        except Exception as e:
            logger.error(f"Error processing group {short_group_key}: {str(e)}")
            raise

    logger.info(
        f"Processed {processed_groups} connector groups, centralized {centralized_count}"
    )

    # Update WorkflowEndpoint references
    _, additional_deletes = _update_workflow_endpoints(
        all_connector_mappings, WorkflowEndpoint
    )
    all_connectors_to_delete.update(additional_deletes)

    # Delete redundant connectors
    _delete_redundant_connectors(all_connectors_to_delete, ConnectorInstance)

    # Final cleanup: Fix any remaining duplicate names within organizations
    _fix_remaining_duplicate_names(ConnectorInstance)

    logger.info(
        f"Migration completed: {centralized_count} centralized connectors created"
    )


def _get_connector_type_from_endpoint(endpoint_type: str) -> str:
    """Map endpoint type to connector type."""
    return "INPUT" if endpoint_type == "SOURCE" else "OUTPUT"


def _find_unused_connectors(
    centralized_connectors: Any, workflow_endpoint_model: Any, total_connectors: int
) -> list[Any]:
    """Find centralized connectors that have no endpoint references."""
    unused_connectors = []
    processed_connectors = 0

    for centralized_connector in centralized_connectors:
        processed_connectors += 1

        endpoints = workflow_endpoint_model.objects.filter(
            connector_instance=centralized_connector
        )

        if not endpoints.exists():
            logger.info(
                f"[{processed_connectors}/{total_connectors}] Centralized connector "
                f"'{centralized_connector}' has no endpoints, marking for deletion"
            )
            unused_connectors.append(centralized_connector.id)

    return unused_connectors


def _create_workflow_specific_connector(
    centralized_connector: Any,
    workflow: Any,
    connector_type: str,
    connector_instance_model: Any,
) -> Any:
    """Create a new workflow-specific connector from a centralized one."""
    try:
        # Try to access connector_metadata to ensure it's readable
        metadata = centralized_connector.connector_metadata
        return connector_instance_model.objects.create(
            connector_name=centralized_connector.connector_name,
            connector_id=centralized_connector.connector_id,
            connector_metadata=metadata,
            connector_version=centralized_connector.connector_version,
            connector_type=connector_type,
            connector_auth=centralized_connector.connector_auth,
            connector_mode=centralized_connector.connector_mode,
            workflow=workflow,
            organization=centralized_connector.organization,
            created_by=centralized_connector.created_by,
            modified_by=centralized_connector.modified_by,
        )
    except Exception as e:
        logger.warning(
            f"Skipping creation of workflow-specific connector from {centralized_connector.id} "
            f"due to encryption error: {str(e)}"
        )
        raise


def _process_connector_endpoints(
    centralized_connector: Any,
    endpoints: Any,
    connector_instance_model: Any,
    processed_count: int,
    total_count: int,
) -> int:
    """Process endpoints for a centralized connector, creating workflow-specific copies."""
    endpoint_ref_count = endpoints.count()
    added_connector_count = 0

    logger.info(
        f"[{processed_count}/{total_count}] Centralized connector "
        f"'{centralized_connector}' has {endpoint_ref_count} endpoint(s) to process"
    )

    # Process each endpoint, reusing the last connector to avoid unnecessary creation
    for index, endpoint in enumerate(endpoints):
        workflow = endpoint.workflow
        endpoint_type = endpoint.endpoint_type
        connector_type = _get_connector_type_from_endpoint(endpoint_type)

        if index == endpoint_ref_count - 1:
            # Last endpoint reuses the existing centralized connector
            centralized_connector.workflow = workflow
            centralized_connector.connector_type = connector_type
            centralized_connector.save()
            logger.debug(f"Reused centralized connector for endpoint {endpoint.id}")
        else:
            # Create new workflow-specific connector for other endpoints
            endpoint_connector = _create_workflow_specific_connector(
                centralized_connector, workflow, connector_type, connector_instance_model
            )
            added_connector_count += 1
            endpoint.connector_instance = endpoint_connector
            endpoint.save()
            logger.debug(f"Created new connector for endpoint {endpoint.id}")

    return added_connector_count


def _delete_unused_centralized_connectors(
    unused_connector_ids: list[Any], connector_instance_model: Any
) -> int:
    """Delete unused centralized connectors in bulk."""
    if not unused_connector_ids:
        logger.info("No unused centralized connectors to delete")
        return 0

    try:
        delete_count = connector_instance_model.objects.filter(
            id__in=unused_connector_ids
        ).delete()[0]
        logger.info(f"Deleted {delete_count} unused centralized connectors")
        return delete_count
    except Exception as e:
        logger.error(f"Error deleting unused connectors: {str(e)}")
        raise


def reverse_centralized_connectors(apps, schema_editor):  # noqa: ARG001
    """Reverse the migration by converting centralized connectors back to workflow-specific ones.

    This is a best-effort reversal that:
    1. Finds all centralized connectors
    2. For each WorkflowEndpoint using a centralized connector, creates a workflow-specific copy
    3. Updates the WorkflowEndpoint to use the workflow-specific copy
    """
    ConnectorInstance = apps.get_model("connector_v2", "ConnectorInstance")  # NOSONAR
    WorkflowEndpoint = apps.get_model("endpoint_v2", "WorkflowEndpoint")  # NOSONAR

    # Get all centralized connectors, but defer the encrypted metadata field to avoid
    # automatic decryption failures when the encryption key has changed
    centralized_connectors = (
        ConnectorInstance.objects.prefetch_related("workflow_endpoints")
        .defer("connector_metadata")
        .all()
    )

    total_connectors = centralized_connectors.count()
    logger.info(f"Processing {total_connectors} centralized connectors for reversal")

    # Find unused connectors that can be deleted
    unused_connectors = _find_unused_connectors(
        centralized_connectors, WorkflowEndpoint, total_connectors
    )

    # Process connectors with endpoints to create workflow-specific copies
    added_connector_count = 0
    processed_connectors = 0
    skipped_reverse_connectors = 0

    for centralized_connector in centralized_connectors:
        processed_connectors += 1

        # Skip connectors already marked for deletion
        if centralized_connector.id in unused_connectors:
            continue

        try:
            # Test if we can access encrypted fields before processing
            try:
                _ = centralized_connector.connector_metadata
            except Exception as decrypt_error:
                logger.warning(
                    f"Skipping reverse migration for connector {centralized_connector.id} "
                    f"due to encryption error: {str(decrypt_error)}"
                )
                skipped_reverse_connectors += 1
                continue

            endpoints = WorkflowEndpoint.objects.filter(
                connector_instance=centralized_connector
            )

            if endpoints.exists():
                connector_count = _process_connector_endpoints(
                    centralized_connector,
                    endpoints,
                    ConnectorInstance,
                    processed_connectors,
                    total_connectors,
                )
                added_connector_count += connector_count

        except Exception as e:
            logger.error(
                f"Error processing connector {centralized_connector.id}: {str(e)}"
            )
            raise

    if skipped_reverse_connectors > 0:
        logger.warning(
            f"Skipped {skipped_reverse_connectors} connectors during reverse migration due to encryption issues"
        )

        # Safety check for reverse migration: if we skipped everything, abort
        if skipped_reverse_connectors == total_connectors and total_connectors > 0:
            error_msg = (
                f"CRITICAL: All {total_connectors} connectors were skipped during reverse migration "
                f"due to encryption errors. This likely means the ENCRYPTION_KEY has changed. "
                f"Please restore the correct ENCRYPTION_KEY and retry the reverse migration. "
                f"The reverse migration has been aborted to prevent data loss."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    # Delete unused centralized connectors
    _delete_unused_centralized_connectors(unused_connectors, ConnectorInstance)

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
