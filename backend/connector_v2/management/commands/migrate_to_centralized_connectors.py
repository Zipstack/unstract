"""
Management command to migrate existing connectors to centralized connectors.
"""

import hashlib
from django.core.management.base import BaseCommand
from django.db import transaction
from connector_v2.models import ConnectorInstance
from workflow_manager.endpoint_v2.models import WorkflowEndpoint


class Command(BaseCommand):
    help = 'Migrate existing workflow-specific connectors to centralized connectors'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Find all existing connectors that are workflow-specific
        workflow_connectors = ConnectorInstance.objects.filter(
            workflow__isnull=False,
            is_shared=False
        )
        
        if not workflow_connectors.exists():
            self.stdout.write(self.style.SUCCESS('No workflow-specific connectors found. Migration not needed.'))
            return
        
        self.stdout.write(f'Found {workflow_connectors.count()} workflow-specific connectors')
        
        # Dictionary to store mapping from old connector to new shared connector
        connector_mapping = {}
        
        # Group connectors by organization and unique credential fingerprint
        connector_groups = {}
        
        for connector in workflow_connectors:
            # Create unique key based on connector properties
            metadata_hash = None
            if connector.connector_metadata:
                # Convert memoryview to bytes if needed
                metadata_bytes = connector.connector_metadata
                if isinstance(metadata_bytes, memoryview):
                    metadata_bytes = metadata_bytes.tobytes()
                metadata_hash = hashlib.sha256(metadata_bytes).hexdigest()
            
            group_key = (
                connector.organization_id,
                connector.connector_id,
                connector.connector_type,
                connector.connector_mode,
                metadata_hash
            )
            
            if group_key not in connector_groups:
                connector_groups[group_key] = []
            connector_groups[group_key].append(connector)
        
        self.stdout.write(f'Grouped into {len(connector_groups)} unique connector groups')
        
        created_shared = 0
        updated_endpoints = 0
        
        with transaction.atomic():
            # Create shared connectors for each group
            for group_key, connectors in connector_groups.items():
                if len(connectors) == 1:
                    # Only one connector, make it shared
                    connector = connectors[0]
                    
                    if not dry_run:
                        connector.is_shared = True
                        connector.workflow = None
                        connector.save()
                    
                    connector_mapping[connector.id] = connector
                    created_shared += 1
                    self.stdout.write(f'Made existing connector shared: {connector.connector_name}')
                else:
                    # Multiple connectors with same credentials, create one shared connector
                    template_connector = connectors[0]
                    
                    # Create unique connector name for shared connector
                    base_name = f"{template_connector.connector_name} (Shared)"
                    unique_name = base_name
                    counter = 1
                    
                    # Ensure unique name for shared connector
                    while ConnectorInstance.objects.filter(
                        connector_name=unique_name,
                        organization=template_connector.organization,
                        connector_type=template_connector.connector_type,
                        is_shared=True
                    ).exists():
                        unique_name = f"{base_name} {counter}"
                        counter += 1
                    
                    if not dry_run:
                        # Create new shared connector
                        shared_connector = ConnectorInstance.objects.create(
                            connector_name=unique_name,
                            connector_id=template_connector.connector_id,
                            connector_metadata=template_connector.connector_metadata,
                            connector_version=template_connector.connector_version,
                            connector_type=template_connector.connector_type,
                            connector_auth=template_connector.connector_auth,
                            connector_mode=template_connector.connector_mode,
                            is_shared=True,
                            workflow=None,
                            organization=template_connector.organization,
                            created_by=template_connector.created_by,
                            modified_by=template_connector.modified_by,
                        )
                    else:
                        shared_connector = template_connector  # For dry run
                    
                    # Map all old connectors to the new shared one
                    for connector in connectors:
                        connector_mapping[connector.id] = shared_connector
                    
                    created_shared += 1
                    self.stdout.write(f'Created shared connector: {unique_name}')
            
            if not dry_run:
                # Update WorkflowEndpoint references to use shared connectors
                for old_connector_id, new_connector in connector_mapping.items():
                    endpoints_updated = WorkflowEndpoint.objects.filter(
                        connector_instance_id=old_connector_id
                    ).update(connector_instance=new_connector)
                    updated_endpoints += endpoints_updated
                    
                    if endpoints_updated > 0:
                        self.stdout.write(f'Updated {endpoints_updated} endpoints for connector {old_connector_id}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN: Would create {created_shared} shared connectors and update {len(connector_mapping)} endpoint references'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Successfully created {created_shared} shared connectors and updated {updated_endpoints} endpoint references'
            ))
            
            # Mark old workflow-specific connectors that were replaced
            old_connector_ids = [cid for cid in connector_mapping.keys() 
                               if connector_mapping[cid].id != cid]
            if old_connector_ids:
                ConnectorInstance.objects.filter(
                    id__in=old_connector_ids
                ).update(is_shared=False)
                self.stdout.write(f'Marked {len(old_connector_ids)} old connectors as workflow-specific (legacy)')