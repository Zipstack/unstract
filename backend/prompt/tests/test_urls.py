import pytest
from django.urls import reverse
from prompt.models import Prompt
from rest_framework import status
from rest_framework.test import APITestCase

pytestmark = pytest.mark.django_db


@pytest.mark.prompt
class TestPrompts(APITestCase):
    def test_prompts_list(self):
        """Ensure we can list all prompts."""
        url = reverse("prompts_v1-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_prompts_detail(self):
        """Ensure we can retrieve a single prompt."""
        url = reverse("prompts_v1-detail", kwargs={"pk": 2})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["version_name"], "v0.1.1")

    def test_prompts_detail_throw_404(self):
        """Tests whether a 404 error is thrown on retrieving a prompt."""
        url = reverse("prompts-detail", kwargs={"pk": 200})  # Prompt doesn't exist
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_prompts_create(self):
        """Ensure we can create a new prompt."""
        url = reverse("prompts_v1-list")
        data = {
            "org": 1,
            "project": 1,
            "version_name": "v0.1.2",
            "created_by": 2,
            "modified_by": 2,
            "prompt_input": "You're a CS undergrad looking to receive an admit from a \
                university for a masters in AI, write a convincing SOP",
            "promoted": False,
        }
        response = self.client.post(url, data, format="json")
        pk = response.data["id"]
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Prompt.objects.count(), 3)
        self.assertEqual(Prompt.objects.get(pk=pk).version_name, "v0.1.2")

    def test_prompts_create_throw_bad_request(self):
        """Ensure we throw an error in case of a bad request."""
        url = reverse("prompts_v1-list")
        data = {
            "org": 200,  # This org does not exist
            "project": 1,
            "version_name": "v0.1.2",
            "created_by": 2,
            "modified_by": 2,
            "prompt_input": "You're a CS undergrad looking to receive an admit from a \
                university for a masters in AI, write a convincing SOP",
            "promoted": False,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_prompts_update(self):
        """Tests the PUT method."""
        url = reverse("prompts_v1-detail", kwargs={"pk": 2})
        data = {
            "org": 1,
            "project": 1,
            "version_name": "v0.1.3",
            "created_by": 2,
            "modified_by": 2,
            "prompt_input": "You're a CS undergrad looking to receive an admit from a \
                university for a masters in AI, write a convincing SOP",
            "promoted": False,
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pk = response.data["id"]
        self.assertEqual(Prompt.objects.get(pk=pk).version_name, "v0.1.3")

    def test_prompts_update_bad_request(self):
        """Tests the PUT method for 400 error."""
        url = reverse("prompts_v1-detail", kwargs={"pk": 2})
        data = {
            "org": 200,  # This org does not exist
            "project": 1,
            "version_name": "v0.1.3",
            "created_by": 2,
            "modified_by": 2,
            "prompt_input": "You're a CS undergrad looking to receive an admit from a \
                university for a masters in AI, write a convincing SOP",
            "promoted": False,
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_prompts_partial_update(self):
        """Tests the PATCH method."""
        url = reverse("prompts_v1-detail", kwargs={"pk": 2})
        data = {"promoted": True}
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pk = response.data["id"]
        self.assertEqual(Prompt.objects.get(pk=pk).promoted, True)

    def test_prompts_delete(self):
        """Tests the DELETE method."""
        url = reverse("prompts_v1-detail", kwargs={"pk": 2})
        response = self.client.delete(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Check if data was deleted as well
        url = reverse("prompts_v1-detail", kwargs={"pk": 2})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
