import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from account_v2.models import Organization, User
from connector_v2.models import ConnectorInstance
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.workflow import Workflow
from tool_instance_v2.models import ToolInstance


class SharedConnectorTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create organization and user
        self.organization = Organization.objects.create(
            organization_name="Test Org",
            display_name="Test Organization"
        )
        
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            organization=self.organization
        )
        
        # Mock authentication
        self.client.force_authenticate(user=self.user)

    def test_create_shared_connector(self):
        """Test creating a new shared connector."""
        url = reverse('shared-connector-list')
        
        connector_data = {
            'connector_name': 'Test S3 Connector',
            'connector_id': 'minio|test-uuid',
            'connector_type': 'INPUT',
            'connector_metadata': {
                'key': 'test-key',
                'secret': 'test-secret',
                'endpoint_url': 'https://s3.amazonaws.com',
                'region_name': 'us-east-1'
            }
        }
        
        with patch('connector_v2.views.ConnectorInstance.supportsOAuth', return_value=False):
            response = self.client.post(url, connector_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify connector was created
        connector = ConnectorInstance.objects.get(id=response.data['id'])
        self.assertTrue(connector.is_shared)
        self.assertIsNone(connector.workflow)
        self.assertEqual(connector.organization, self.organization)

    def test_list_shared_connectors(self):
        """Test listing shared connectors."""
        # Create a shared connector
        shared_connector = ConnectorInstance.objects.create(
            connector_name='Shared Connector',
            connector_id='minio|test-uuid',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        # Create a workflow-specific connector (should not appear in shared list)
        workflow = Workflow.objects.create(
            workflow_name='Test Workflow',
            organization=self.organization,
            created_by=self.user
        )
        
        workflow_connector = ConnectorInstance.objects.create(
            connector_name='Workflow Connector',
            connector_id='minio|test-uuid-2',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=False,
            workflow=workflow,
            organization=self.organization,
            created_by=self.user
        )
        
        url = reverse('shared-connector-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should only return shared connector
        connectors = response.data.get('results', response.data)
        self.assertEqual(len(connectors), 1)
        self.assertEqual(connectors[0]['id'], str(shared_connector.id))

    def test_delete_shared_connector_in_use(self):
        """Test that deleting a shared connector in use returns error."""
        # Create shared connector
        shared_connector = ConnectorInstance.objects.create(
            connector_name='In Use Connector',
            connector_id='minio|test-uuid',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        # Create workflow and endpoint that uses this connector
        workflow = Workflow.objects.create(
            workflow_name='Test Workflow',
            organization=self.organization,
            created_by=self.user
        )
        
        WorkflowEndpoint.objects.create(
            workflow=workflow,
            endpoint_type='SOURCE',
            connection_type='FILESYSTEM',
            connector_instance=shared_connector,
            organization=self.organization
        )
        
        url = reverse('shared-connector-detail', args=[shared_connector.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot delete connector', response.data['error'])

    def test_delete_unused_shared_connector(self):
        """Test deleting an unused shared connector succeeds."""
        shared_connector = ConnectorInstance.objects.create(
            connector_name='Unused Connector',
            connector_id='minio|test-uuid',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        url = reverse('shared-connector-detail', args=[shared_connector.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ConnectorInstance.objects.filter(id=shared_connector.id).exists())

    def test_filter_shared_connectors_by_type(self):
        """Test filtering shared connectors by type."""
        # Create INPUT and OUTPUT connectors
        input_connector = ConnectorInstance.objects.create(
            connector_name='Input Connector',
            connector_id='minio|test-uuid-1',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        output_connector = ConnectorInstance.objects.create(
            connector_name='Output Connector',
            connector_id='postgres|test-uuid-1',
            connector_type='OUTPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        # Test filtering by INPUT
        url = reverse('shared-connector-by-type') + '?type=INPUT'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        connectors = response.data
        self.assertEqual(len(connectors), 1)
        self.assertEqual(connectors[0]['connector_type'], 'INPUT')
        
        # Test filtering by OUTPUT
        url = reverse('shared-connector-by-type') + '?type=OUTPUT'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        connectors = response.data
        self.assertEqual(len(connectors), 1)
        self.assertEqual(connectors[0]['connector_type'], 'OUTPUT')

    def test_organization_isolation(self):
        """Test that shared connectors are isolated by organization."""
        # Create another organization
        other_org = Organization.objects.create(
            organization_name="Other Org",
            display_name="Other Organization"
        )
        
        other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
            organization=other_org
        )
        
        # Create connector in other organization
        ConnectorInstance.objects.create(
            connector_name='Other Org Connector',
            connector_id='minio|other-uuid',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=other_org,
            created_by=other_user
        )
        
        # Current user should not see other org's connectors
        url = reverse('shared-connector-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        connectors = response.data.get('results', response.data)
        self.assertEqual(len(connectors), 0)
    
    def test_delete_shared_connector_used_by_tool_instance(self):
        """Test that deleting a shared connector used by tool instances returns error."""
        # Create shared connector
        shared_connector = ConnectorInstance.objects.create(
            connector_name='Tool Used Connector',
            connector_id='minio|tool-uuid',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        # Create workflow and tool instance that uses this connector
        workflow = Workflow.objects.create(
            workflow_name='Test Workflow',
            organization=self.organization,
            created_by=self.user
        )
        
        ToolInstance.objects.create(
            workflow=workflow,
            tool_id='test-tool',
            version='1.0',
            metadata={'test': 'data'},
            step=1,
            input_file_connector=shared_connector,
            created_by=self.user
        )
        
        url = reverse('shared-connector-detail', args=[shared_connector.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot delete connector', response.data['error'])
        self.assertIn('tool instance(s)', response.data['error'])
    
    def test_delete_shared_connector_used_by_multiple_tool_instances(self):
        """Test that deleting a shared connector used by multiple tool instances returns error."""
        # Create shared connector
        shared_connector = ConnectorInstance.objects.create(
            connector_name='Multi Tool Used Connector',
            connector_id='postgres|multi-tool-uuid',
            connector_type='OUTPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        # Create workflow and multiple tool instances that use this connector
        workflow = Workflow.objects.create(
            workflow_name='Multi Tool Workflow',
            organization=self.organization,
            created_by=self.user
        )
        
        # Create tool instances using different connector fields
        ToolInstance.objects.create(
            workflow=workflow,
            tool_id='test-tool-1',
            version='1.0',
            metadata={'test': 'data'},
            step=1,
            output_file_connector=shared_connector,
            created_by=self.user
        )
        
        ToolInstance.objects.create(
            workflow=workflow,
            tool_id='test-tool-2',
            version='1.0',
            metadata={'test': 'data'},
            step=2,
            input_db_connector=shared_connector,
            created_by=self.user
        )
        
        ToolInstance.objects.create(
            workflow=workflow,
            tool_id='test-tool-3',
            version='1.0',
            metadata={'test': 'data'},
            step=3,
            output_db_connector=shared_connector,
            created_by=self.user
        )
        
        url = reverse('shared-connector-detail', args=[shared_connector.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot delete connector', response.data['error'])
        self.assertIn('3 tool instance(s)', response.data['error'])
    
    def test_delete_shared_connector_used_by_both_workflow_and_tool(self):
        """Test that deleting a shared connector used by both workflow endpoints and tool instances returns error."""
        # Create shared connector
        shared_connector = ConnectorInstance.objects.create(
            connector_name='Both Used Connector',
            connector_id='minio|both-uuid',
            connector_type='INPUT',
            connector_metadata=b'encrypted-data',
            is_shared=True,
            organization=self.organization,
            created_by=self.user
        )
        
        # Create workflow
        workflow = Workflow.objects.create(
            workflow_name='Mixed Usage Workflow',
            organization=self.organization,
            created_by=self.user
        )
        
        # Create workflow endpoint that uses this connector
        WorkflowEndpoint.objects.create(
            workflow=workflow,
            endpoint_type='SOURCE',
            connection_type='FILESYSTEM',
            connector_instance=shared_connector,
            organization=self.organization
        )
        
        # Create tool instance that also uses this connector
        ToolInstance.objects.create(
            workflow=workflow,
            tool_id='test-tool',
            version='1.0',
            metadata={'test': 'data'},
            step=1,
            input_file_connector=shared_connector,
            created_by=self.user
        )
        
        url = reverse('shared-connector-detail', args=[shared_connector.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot delete connector', response.data['error'])
        self.assertIn('1 workflow endpoint(s)', response.data['error'])
        self.assertIn('1 tool instance(s)', response.data['error'])
        self.assertIn(' and ', response.data['error'])