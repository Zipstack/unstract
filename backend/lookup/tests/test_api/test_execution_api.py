"""
Tests for Look-Up execution and debug API endpoints.
"""

import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import (
    LookupProject,
    LookupPromptTemplate,
    PromptStudioLookupLink,
    LookupExecutionAudit
)

User = get_user_model()


class LookupExecutionAPITest(TestCase):
    """Test cases for Look-Up execution API."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        # Create template
        self.template = LookupPromptTemplate.objects.create(
            name="Test Template",
            template_text="Vendor: {{vendor_name}}\n{{reference_data}}",
            llm_config={"provider": "openai", "model": "gpt-4"},
            created_by=self.user
        )

        # Create projects
        self.lookup1 = LookupProject.objects.create(
            name="Vendor Lookup",
            description="Vendor enrichment",
            reference_data_type="vendor_catalog",
            template=self.template,
            created_by=self.user
        )
        self.lookup2 = LookupProject.objects.create(
            name="Product Lookup",
            description="Product enrichment",
            reference_data_type="product_catalog",
            template=self.template,
            created_by=self.user
        )

        # Create PS project and links
        self.ps_project_id = uuid.uuid4()
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup2
        )

    @patch('lookup.views.LookUpOrchestrator')
    @patch('lookup.views.LookUpExecutor')
    def test_debug_with_ps_project(self, mock_executor_class, mock_orchestrator_class):
        """Test debug execution with PS project context."""
        # Mock the execution
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_lookups.return_value = {
            'lookup_enrichment': {
                'canonical_vendor': 'Test Vendor',
                'vendor_category': 'SaaS',
                'product_type': 'Software'
            },
            '_lookup_metadata': {
                'lookups_executed': 2,
                'successful_lookups': 2,
                'failed_lookups': 0,
                'execution_time_ms': 250,
                'conflicts_resolved': 0
            }
        }

        url = reverse('lookup:lookupdebug-test-with-ps-project')
        data = {
            'prompt_studio_project_id': str(self.ps_project_id),
            'input_data': {
                'vendor_name': 'Test Vendor Inc',
                'product_id': 'PROD-123'
            }
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('lookup_enrichment', response.data)
        self.assertIn('canonical_vendor', response.data['lookup_enrichment'])
        self.assertEqual(response.data['_lookup_metadata']['lookups_executed'], 2)

        # Verify orchestrator was called with correct projects
        mock_orchestrator.execute_lookups.assert_called_once()
        call_args = mock_orchestrator.execute_lookups.call_args
        self.assertEqual(len(call_args.kwargs['lookup_projects']), 2)

    def test_debug_without_ps_project_id(self):
        """Test debug endpoint requires PS project ID."""
        url = reverse('lookup:lookupdebug-test-with-ps-project')
        data = {'input_data': {}}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('prompt_studio_project_id is required', response.data['error'])

    def test_debug_with_no_linked_lookups(self):
        """Test debug with PS project that has no linked Look-Ups."""
        unlinked_ps_id = uuid.uuid4()

        url = reverse('lookup:lookupdebug-test-with-ps-project')
        data = {
            'prompt_studio_project_id': str(unlinked_ps_id),
            'input_data': {}
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'No Look-Ups linked to this Prompt Studio project')
        self.assertEqual(response.data['lookup_enrichment'], {})
        self.assertEqual(response.data['_lookup_metadata']['lookups_executed'], 0)

    @patch('lookup.views.LookUpOrchestrator')
    def test_debug_with_execution_error(self, mock_orchestrator_class):
        """Test debug endpoint handles execution errors gracefully."""
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_lookups.side_effect = Exception("Test error")

        url = reverse('lookup:lookupdebug-test-with-ps-project')
        data = {
            'prompt_studio_project_id': str(self.ps_project_id),
            'input_data': {}
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('Test error', response.data['error'])


class LookupAuditAPITest(TestCase):
    """Test cases for execution audit API."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        # Create template and project
        self.template = LookupPromptTemplate.objects.create(
            name="Test Template",
            template_text="{{reference_data}}",
            llm_config={"provider": "openai", "model": "gpt-4"},
            created_by=self.user
        )

        self.lookup = LookupProject.objects.create(
            name="Test Lookup",
            description="Test",
            reference_data_type="vendor_catalog",
            template=self.template,
            created_by=self.user
        )

        # Create audit records
        self.execution_id = str(uuid.uuid4())

        self.audit1 = LookupExecutionAudit.objects.create(
            lookup_project=self.lookup,
            prompt_studio_project_id=uuid.uuid4(),
            execution_id=self.execution_id,
            input_data={'vendor': 'Test1'},
            enriched_output={'canonical_vendor': 'Test'},
            reference_data_version=1,
            llm_provider='openai',
            llm_model='gpt-4',
            llm_prompt='Test prompt',
            llm_response='{"canonical_vendor": "Test"}',
            llm_response_cached=False,
            execution_time_ms=150,
            llm_call_time_ms=100,
            status='success',
            confidence_score=Decimal('0.95')
        )

        self.audit2 = LookupExecutionAudit.objects.create(
            lookup_project=self.lookup,
            prompt_studio_project_id=uuid.uuid4(),
            execution_id=str(uuid.uuid4()),
            input_data={'vendor': 'Test2'},
            status='failure',
            error_message='LLM timeout'
        )

    def test_list_audit_records(self):
        """Test listing all audit records."""
        url = reverse('lookup:executionaudit-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_filter_audits_by_lookup_project(self):
        """Test filtering audits by Look-Up project."""
        url = reverse('lookup:executionaudit-list')
        response = self.client.get(url, {'lookup_project_id': str(self.lookup.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_filter_audits_by_execution_id(self):
        """Test filtering audits by execution ID."""
        url = reverse('lookup:executionaudit-list')
        response = self.client.get(url, {'execution_id': self.execution_id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['execution_id'], self.execution_id)

    def test_filter_audits_by_status(self):
        """Test filtering audits by status."""
        url = reverse('lookup:executionaudit-list')

        # Get successful executions
        response = self.client.get(url, {'status': 'success'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['status'], 'success')

        # Get failed executions
        response = self.client.get(url, {'status': 'failure'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['status'], 'failure')

    def test_retrieve_audit_record(self):
        """Test retrieving a specific audit record."""
        url = reverse('lookup:executionaudit-detail', args=[self.audit1.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['execution_id'], self.execution_id)
        self.assertEqual(response.data['status'], 'success')

    def test_audit_records_are_readonly(self):
        """Test that audit records cannot be modified."""
        url = reverse('lookup:executionaudit-detail', args=[self.audit1.id])

        # Try to update
        response = self.client.patch(url, {'status': 'modified'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Try to delete
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @patch('lookup.views.AuditLogger')
    def test_get_statistics(self, mock_logger_class):
        """Test getting execution statistics."""
        mock_logger = MagicMock()
        mock_logger_class.return_value = mock_logger
        mock_logger.get_project_stats.return_value = {
            'total_executions': 100,
            'success_rate': 0.95,
            'avg_execution_time_ms': 150.5,
            'cache_hit_rate': 0.30,
            'avg_confidence_score': 0.92
        }

        url = reverse('lookup:executionaudit-statistics')
        response = self.client.get(url, {'lookup_project_id': str(self.lookup.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_executions'], 100)
        self.assertEqual(response.data['success_rate'], 0.95)

    def test_statistics_requires_project_id(self):
        """Test that statistics endpoint requires project ID."""
        url = reverse('lookup:executionaudit-statistics')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('lookup_project_id is required', response.data['error'])
