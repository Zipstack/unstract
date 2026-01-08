"""
Tests for Prompt Studio Look-Up linking API endpoints.
"""

import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import (
    LookupProject,
    LookupPromptTemplate,
    PromptStudioLookupLink
)

User = get_user_model()


class PromptStudioLinkingAPITest(TestCase):
    """Test cases for PS Look-Up linking API."""

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
            template_text="{{reference_data}}",
            llm_config={"provider": "openai", "model": "gpt-4"},
            created_by=self.user
        )

        # Create Look-Up projects
        self.lookup1 = LookupProject.objects.create(
            name="Lookup 1",
            description="First lookup",
            template=self.template,
            created_by=self.user
        )
        self.lookup2 = LookupProject.objects.create(
            name="Lookup 2",
            description="Second lookup",
            template=self.template,
            created_by=self.user
        )

        # Create PS project ID
        self.ps_project_id = uuid.uuid4()

    def test_create_link(self):
        """Test creating a link between PS project and Look-Up."""
        url = reverse('lookup:lookuplink-list')
        data = {
            'prompt_studio_project_id': str(self.ps_project_id),
            'lookup_project': str(self.lookup1.id)
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['lookup_project_name'], 'Lookup 1')
        self.assertTrue(
            PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=self.ps_project_id,
                lookup_project=self.lookup1
            ).exists()
        )

    def test_create_duplicate_link(self):
        """Test that duplicate links are rejected."""
        # Create first link
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )

        # Try to create duplicate
        url = reverse('lookup:lookuplink-list')
        data = {
            'prompt_studio_project_id': str(self.ps_project_id),
            'lookup_project': str(self.lookup1.id)
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already linked', str(response.data))

    def test_list_links(self):
        """Test listing all links."""
        # Create links
        link1 = PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )
        link2 = PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup2
        )

        url = reverse('lookup:lookuplink-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_filter_links_by_ps_project(self):
        """Test filtering links by PS project ID."""
        # Create links for different PS projects
        ps_project_id_2 = uuid.uuid4()

        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=ps_project_id_2,
            lookup_project=self.lookup2
        )

        url = reverse('lookup:lookuplink-list')
        response = self.client.get(url, {'prompt_studio_project_id': str(self.ps_project_id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['lookup_project_name'], 'Lookup 1')

    def test_filter_links_by_lookup_project(self):
        """Test filtering links by Look-Up project ID."""
        # Create links
        ps_project_id_2 = uuid.uuid4()

        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=ps_project_id_2,
            lookup_project=self.lookup1
        )

        url = reverse('lookup:lookuplink-list')
        response = self.client.get(url, {'lookup_project_id': str(self.lookup1.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_delete_link(self):
        """Test deleting a link."""
        link = PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )

        url = reverse('lookup:lookuplink-detail', args=[link.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            PromptStudioLookupLink.objects.filter(id=link.id).exists()
        )

    def test_bulk_link(self):
        """Test bulk linking multiple Look-Ups to a PS project."""
        url = reverse('lookup:lookuplink-bulk-link')
        data = {
            'prompt_studio_project_id': str(self.ps_project_id),
            'lookup_project_ids': [str(self.lookup1.id), str(self.lookup2.id)],
            'unlink': False
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_processed'], 2)
        self.assertTrue(response.data['results'][0]['linked'])
        self.assertTrue(response.data['results'][1]['linked'])

        # Verify links were created
        self.assertEqual(
            PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=self.ps_project_id
            ).count(),
            2
        )

    def test_bulk_unlink(self):
        """Test bulk unlinking Look-Ups from a PS project."""
        # Create links first
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup2
        )

        url = reverse('lookup:lookuplink-bulk-link')
        data = {
            'prompt_studio_project_id': str(self.ps_project_id),
            'lookup_project_ids': [str(self.lookup1.id), str(self.lookup2.id)],
            'unlink': True
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_processed'], 2)
        self.assertTrue(response.data['results'][0]['unlinked'])
        self.assertTrue(response.data['results'][1]['unlinked'])

        # Verify links were removed
        self.assertEqual(
            PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=self.ps_project_id
            ).count(),
            0
        )

    def test_bulk_link_idempotent(self):
        """Test that bulk link is idempotent."""
        # Create one link first
        PromptStudioLookupLink.objects.create(
            prompt_studio_project_id=self.ps_project_id,
            lookup_project=self.lookup1
        )

        url = reverse('lookup:lookuplink-bulk-link')
        data = {
            'prompt_studio_project_id': str(self.ps_project_id),
            'lookup_project_ids': [str(self.lookup1.id), str(self.lookup2.id)],
            'unlink': False
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_processed'], 2)
        self.assertFalse(response.data['results'][0]['linked'])  # Already existed
        self.assertTrue(response.data['results'][1]['linked'])  # Newly created

        # Still only 2 links total
        self.assertEqual(
            PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=self.ps_project_id
            ).count(),
            2
        )
