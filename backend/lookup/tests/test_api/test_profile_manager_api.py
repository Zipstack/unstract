"""
Tests for LookupProfileManager API endpoints.
"""

import uuid
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import LookupProject, LookupProfileManager

User = get_user_model()


class LookupProfileManagerAPITest(TestCase):
    """Test cases for LookupProfileManager API."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        # Create lookup project
        self.project = LookupProject.objects.create(
            name="Test Lookup Project",
            description="Test Description",
            reference_data_type="vendor_catalog",
            created_by=self.user
        )

        # Mock adapter instances (UUIDs)
        self.mock_llm_id = str(uuid.uuid4())
        self.mock_embedding_id = str(uuid.uuid4())
        self.mock_vector_db_id = str(uuid.uuid4())
        self.mock_x2text_id = str(uuid.uuid4())

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    def test_create_profile(self, mock_get_adapter):
        """Test creating a new profile."""
        # Mock adapter instances
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        url = reverse('lookup:lookupprofile-list')
        data = {
            'profile_name': 'Default Profile',
            'lookup_project': str(self.project.id),
            'llm': self.mock_llm_id,
            'embedding_model': self.mock_embedding_id,
            'vector_store': self.mock_vector_db_id,
            'x2text': self.mock_x2text_id,
            'chunk_size': 1000,
            'chunk_overlap': 200,
            'similarity_top_k': 5,
            'is_default': True
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['profile_name'], 'Default Profile')
        self.assertTrue(response.data['is_default'])
        self.assertEqual(LookupProfileManager.objects.count(), 1)

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    def test_duplicate_profile_name(self, mock_get_adapter):
        """Test that duplicate profile names for same project are rejected."""
        # Mock adapter instances
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        # Create first profile
        LookupProfileManager.objects.create(
            profile_name='Test Profile',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            created_by=self.user
        )

        # Try to create duplicate
        url = reverse('lookup:lookupprofile-list')
        data = {
            'profile_name': 'Test Profile',  # Same name
            'lookup_project': str(self.project.id),  # Same project
            'llm': self.mock_llm_id,
            'embedding_model': self.mock_embedding_id,
            'vector_store': self.mock_vector_db_id,
            'x2text': self.mock_x2text_id,
        }

        response = self.client.post(url, data, format='json')

        # Should fail due to unique constraint
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    @patch('adapter_processor_v2.adapter_processor.AdapterProcessor.get_adapter_instance_by_id')
    def test_list_profiles(self, mock_get_by_id, mock_get_adapter):
        """Test listing all profiles."""
        # Mock adapters
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        mock_adapter_detail = {
            'id': str(uuid.uuid4()),
            'adapter_name': 'Test Adapter',
            'adapter_type': 'LLM'
        }
        mock_get_by_id.return_value = mock_adapter_detail

        # Create test profiles
        LookupProfileManager.objects.create(
            profile_name='Profile 1',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            created_by=self.user
        )

        LookupProfileManager.objects.create(
            profile_name='Profile 2',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            created_by=self.user
        )

        url = reverse('lookup:lookupprofile-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    @patch('adapter_processor_v2.adapter_processor.AdapterProcessor.get_adapter_instance_by_id')
    def test_filter_by_project(self, mock_get_by_id, mock_get_adapter):
        """Test filtering profiles by project."""
        # Mock adapters
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        mock_adapter_detail = {
            'id': str(uuid.uuid4()),
            'adapter_name': 'Test Adapter',
            'adapter_type': 'LLM'
        }
        mock_get_by_id.return_value = mock_adapter_detail

        # Create another project
        project2 = LookupProject.objects.create(
            name="Project 2",
            description="Description 2",
            reference_data_type="product_catalog",
            created_by=self.user
        )

        # Create profiles for different projects
        LookupProfileManager.objects.create(
            profile_name='Profile 1',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            created_by=self.user
        )

        LookupProfileManager.objects.create(
            profile_name='Profile 2',
            lookup_project=project2,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            created_by=self.user
        )

        # Filter by project 1
        url = reverse('lookup:lookupprofile-list')
        response = self.client.get(url, {'lookup_project': str(self.project.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['profile_name'], 'Profile 1')

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    @patch('adapter_processor_v2.adapter_processor.AdapterProcessor.get_adapter_instance_by_id')
    def test_get_default_profile(self, mock_get_by_id, mock_get_adapter):
        """Test getting the default profile for a project."""
        # Mock adapters
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        mock_adapter_detail = {
            'id': str(uuid.uuid4()),
            'adapter_name': 'Test Adapter',
            'adapter_type': 'LLM'
        }
        mock_get_by_id.return_value = mock_adapter_detail

        # Create profiles
        profile1 = LookupProfileManager.objects.create(
            profile_name='Non-Default',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            is_default=False,
            created_by=self.user
        )

        profile2 = LookupProfileManager.objects.create(
            profile_name='Default Profile',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            is_default=True,
            created_by=self.user
        )

        # Get default profile
        url = reverse('lookup:lookupprofile-default')
        response = self.client.get(url, {'lookup_project': str(self.project.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['profile_name'], 'Default Profile')
        self.assertTrue(response.data['is_default'])

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    @patch('adapter_processor_v2.adapter_processor.AdapterProcessor.get_adapter_instance_by_id')
    def test_set_default_profile(self, mock_get_by_id, mock_get_adapter):
        """Test setting a profile as default."""
        # Mock adapters
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        mock_adapter_detail = {
            'id': str(uuid.uuid4()),
            'adapter_name': 'Test Adapter',
            'adapter_type': 'LLM'
        }
        mock_get_by_id.return_value = mock_adapter_detail

        # Create two profiles
        profile1 = LookupProfileManager.objects.create(
            profile_name='Profile 1',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            is_default=True,
            created_by=self.user
        )

        profile2 = LookupProfileManager.objects.create(
            profile_name='Profile 2',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            is_default=False,
            created_by=self.user
        )

        # Set profile2 as default
        url = reverse('lookup:lookupprofile-set-default', args=[profile2.profile_id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_default'])

        # Verify profile1 is no longer default
        profile1.refresh_from_db()
        self.assertFalse(profile1.is_default)

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    @patch('adapter_processor_v2.adapter_processor.AdapterProcessor.get_adapter_instance_by_id')
    def test_update_profile(self, mock_get_by_id, mock_get_adapter):
        """Test updating a profile."""
        # Mock adapters
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        mock_adapter_detail = {
            'id': str(uuid.uuid4()),
            'adapter_name': 'Test Adapter',
            'adapter_type': 'LLM'
        }
        mock_get_by_id.return_value = mock_adapter_detail

        # Create profile
        profile = LookupProfileManager.objects.create(
            profile_name='Original Name',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            chunk_size=1000,
            created_by=self.user
        )

        # Update profile
        url = reverse('lookup:lookupprofile-detail', args=[profile.profile_id])
        data = {
            'chunk_size': 2000,
            'chunk_overlap': 300,
            'similarity_top_k': 10
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['chunk_size'], 2000)
        self.assertEqual(response.data['chunk_overlap'], 300)
        self.assertEqual(response.data['similarity_top_k'], 10)

    @patch('adapter_processor_v2.models.AdapterInstance.objects.get')
    def test_delete_profile(self, mock_get_adapter):
        """Test deleting a profile."""
        # Mock adapter instances
        mock_adapter = MagicMock()
        mock_adapter.id = uuid.uuid4()
        mock_get_adapter.return_value = mock_adapter

        # Create profile
        profile = LookupProfileManager.objects.create(
            profile_name='To Delete',
            lookup_project=self.project,
            llm_id=self.mock_llm_id,
            embedding_model_id=self.mock_embedding_id,
            vector_store_id=self.mock_vector_db_id,
            x2text_id=self.mock_x2text_id,
            created_by=self.user
        )

        url = reverse('lookup:lookupprofile-detail', args=[profile.profile_id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(LookupProfileManager.objects.count(), 0)

    def test_get_default_profile_no_default_exists(self):
        """Test getting default profile when none exists."""
        url = reverse('lookup:lookupprofile-default')
        response = self.client.get(url, {'lookup_project': str(self.project.id)})

        # Should return 404 when no default profile exists
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_required_adapters(self):
        """Test that all 4 adapters are required."""
        url = reverse('lookup:lookupprofile-list')

        # Missing x2text adapter
        data = {
            'profile_name': 'Incomplete Profile',
            'lookup_project': str(self.project.id),
            'llm': self.mock_llm_id,
            'embedding_model': self.mock_embedding_id,
            'vector_store': self.mock_vector_db_id,
            # Missing x2text
        }

        response = self.client.post(url, data, format='json')

        # Should fail validation
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('x2text', str(response.data))
