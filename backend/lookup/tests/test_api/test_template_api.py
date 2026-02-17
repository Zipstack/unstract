"""
Tests for Look-Up Template API endpoints.
"""

from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import LookupPromptTemplate

User = get_user_model()


class LookupTemplateAPITest(TestCase):
    """Test cases for Look-Up Template API."""

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

    def test_list_templates(self):
        """Test listing all templates."""
        url = reverse('lookup:lookuptemplate-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Test Template')

    def test_create_template(self):
        """Test creating a new template."""
        url = reverse('lookup:lookuptemplate-list')
        data = {
            'name': 'New Template',
            'template_text': 'Product: {{product_name}}\n{{reference_data}}',
            'llm_config': {'provider': 'anthropic', 'model': 'claude-2'},
            'is_active': True
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Template')
        self.assertEqual(LookupPromptTemplate.objects.count(), 2)

    def test_create_template_without_reference_placeholder(self):
        """Test that template without {{reference_data}} is rejected."""
        url = reverse('lookup:lookuptemplate-list')
        data = {
            'name': 'Invalid Template',
            'template_text': 'Product: {{product_name}}',  # Missing {{reference_data}}
            'llm_config': {'provider': 'openai', 'model': 'gpt-4'}
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('template_text', response.data)

    def test_create_template_invalid_llm_config(self):
        """Test that template with invalid LLM config is rejected."""
        url = reverse('lookup:lookuptemplate-list')
        data = {
            'name': 'Invalid Config Template',
            'template_text': '{{reference_data}}',
            'llm_config': {'model': 'gpt-4'}  # Missing provider
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('llm_config', response.data)

    def test_update_template(self):
        """Test updating a template."""
        url = reverse('lookup:lookuptemplate-detail', args=[self.template.id])
        data = {
            'name': 'Updated Template',
            'is_active': False
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Template')
        self.assertFalse(response.data['is_active'])

    def test_delete_template(self):
        """Test deleting a template."""
        url = reverse('lookup:lookuptemplate-detail', args=[self.template.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(LookupPromptTemplate.objects.count(), 0)

    @patch('lookup.views.VariableResolver')
    def test_validate_template(self, mock_resolver_class):
        """Test template validation endpoint."""
        # Mock the variable resolver
        mock_resolver = MagicMock()
        mock_resolver_class.return_value = mock_resolver
        mock_resolver.resolve.return_value = "Resolved template text"
        mock_resolver.get_all_variables.return_value = {'vendor_name', 'product_id'}

        url = reverse('lookup:lookuptemplate-validate')
        data = {
            'template_text': 'Vendor: {{vendor_name}}\nProduct: {{product_id}}\n{{reference_data}}',
            'sample_data': {'vendor_name': 'Test Vendor', 'product_id': '123'},
            'sample_reference': 'Sample reference data'
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['valid'])
        self.assertIn('resolved_template', response.data)
        self.assertIn('variables_found', response.data)
        self.assertEqual(set(response.data['variables_found']), {'vendor_name', 'product_id'})

    def test_validate_template_with_error(self):
        """Test template validation with error."""
        url = reverse('lookup:lookuptemplate-validate')
        data = {
            'template_text': 'Invalid: {{unclosed_variable',  # Invalid template
            'sample_data': {}
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['valid'])
        self.assertIn('error', response.data)

    def test_filter_templates_by_active_status(self):
        """Test filtering templates by active status."""
        # Create inactive template
        LookupPromptTemplate.objects.create(
            name="Inactive Template",
            template_text="{{reference_data}}",
            llm_config={"provider": "openai", "model": "gpt-4"},
            is_active=False,
            created_by=self.user
        )

        url = reverse('lookup:lookuptemplate-list')

        # Get only active templates
        response = self.client.get(url, {'is_active': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Test Template')

        # Get only inactive templates
        response = self.client.get(url, {'is_active': 'false'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Inactive Template')
