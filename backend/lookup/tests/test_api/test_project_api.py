"""
Tests for Look-Up Project API endpoints.
"""

import json
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import LookupProject, LookupPromptTemplate, LookupDataSource

User = get_user_model()


class LookupProjectAPITest(TestCase):
    """Test cases for Look-Up Project API."""

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
            template_text="Vendor: {{vendor_name}}\nReference: {{reference_data}}",
            llm_config={"provider": "openai", "model": "gpt-4"},
            created_by=self.user
        )

        # Create project
        self.project = LookupProject.objects.create(
            name="Test Project",
            description="Test Description",
            template=self.template,
            created_by=self.user
        )

    def test_list_projects(self):
        """Test listing all projects."""
        url = reverse('lookup:lookupproject-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Test Project')

    def test_create_project(self):
        """Test creating a new project."""
        url = reverse('lookup:lookupproject-list')
        data = {
            'name': 'New Project',
            'description': 'New Description',
            'template_id': str(self.template.id),
            'is_active': True
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Project')
        self.assertEqual(LookupProject.objects.count(), 2)

    def test_retrieve_project(self):
        """Test retrieving a specific project."""
        url = reverse('lookup:lookupproject-detail', args=[self.project.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Project')
        self.assertIn('template', response.data)

    def test_update_project(self):
        """Test updating a project."""
        url = reverse('lookup:lookupproject-detail', args=[self.project.id])
        data = {
            'name': 'Updated Project',
            'description': 'Updated Description',
            'is_active': False
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Project')
        self.assertFalse(response.data['is_active'])

    def test_delete_project(self):
        """Test deleting a project."""
        url = reverse('lookup:lookupproject-detail', args=[self.project.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(LookupProject.objects.count(), 0)

    @patch('lookup.views.LookUpOrchestrator')
    def test_execute_project(self, mock_orchestrator_class):
        """Test executing a Look-Up project."""
        # Mock the orchestrator
        mock_orchestrator = MagicMock()
        mock_orchestrator_class.return_value = mock_orchestrator
        mock_orchestrator.execute_lookups.return_value = {
            'lookup_enrichment': {
                'canonical_vendor': 'Test Vendor',
                'vendor_category': 'SaaS'
            },
            '_lookup_metadata': {
                'lookups_executed': 1,
                'successful_lookups': 1,
                'execution_time_ms': 150
            }
        }

        url = reverse('lookup:lookupproject-execute', args=[self.project.id])
        data = {
            'input_data': {'vendor_name': 'Test Vendor Inc'},
            'use_cache': True,
            'timeout_seconds': 30
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('lookup_enrichment', response.data)
        self.assertIn('_lookup_metadata', response.data)

    def test_execute_project_without_auth(self):
        """Test that unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        url = reverse('lookup:lookupproject-execute', args=[self.project.id])
        data = {'input_data': {}}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_filter_projects_by_active_status(self):
        """Test filtering projects by active status."""
        # Create inactive project
        LookupProject.objects.create(
            name="Inactive Project",
            description="Inactive",
            is_active=False,
            created_by=self.user
        )

        url = reverse('lookup:lookupproject-list')
        response = self.client.get(url, {'is_active': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Test Project')

    def test_upload_reference_data(self):
        """Test uploading reference data."""
        url = reverse('lookup:lookupproject-upload-reference-data', args=[self.project.id])

        # Create a mock file
        from django.core.files.uploadedfile import SimpleUploadedFile
        file_content = b"vendor1,category1\nvendor2,category2"
        file = SimpleUploadedFile("vendors.csv", file_content, content_type="text/csv")

        data = {
            'file': file,
            'extract_text': True,
            'metadata': json.dumps({'source': 'manual_upload'})
        }

        response = self.client.post(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('source_file_path', response.data)
        self.assertEqual(response.data['extraction_status'], 'pending')

    def test_list_data_sources(self):
        """Test listing data sources for a project."""
        # Create data sources
        LookupDataSource.objects.create(
            project=self.project,
            source_file_path="test/file1.csv",
            extraction_status='complete',
            version=1,
            is_latest=False
        )
        LookupDataSource.objects.create(
            project=self.project,
            source_file_path="test/file2.csv",
            extraction_status='complete',
            version=2,
            is_latest=True
        )

        url = reverse('lookup:lookupproject-data-sources', args=[self.project.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # Test filtering by is_latest
        response = self.client.get(url, {'is_latest': 'true'})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['version'], 2)
