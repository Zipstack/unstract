import pytest
from django.urls import reverse
from project.models import Project
from rest_framework import status
from rest_framework.test import APITestCase

pytestmark = pytest.mark.django_db


@pytest.mark.project
class TestProjects(APITestCase):
    def test_projects_list(self) -> None:
        """Tests to List the projects."""
        url = reverse("projects_v1-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_projects_detail(self) -> None:
        """Tests to fetch a project with given pk."""
        url = reverse("projects_v1-detail", kwargs={"pk": 1})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_projects_detail_not_found(self) -> None:
        """Tests for negative case to fetch non exiting key."""
        url = reverse("projects_v1-detail", kwargs={"pk": 768})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_projects_create(self) -> None:
        """Tests to create a new project."""
        url = reverse("projects_v1-list")
        data = {
            "org": 1,
            "project_name": "Unstract Test",
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Project.objects.count(), 2)

    def test_projects_create_bad_request(self) -> None:
        """Tests for negative case to throw error on a wrong access."""
        url = reverse("projects_v1-list")
        data = {
            "project_name": "Unstract Test",
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_projects_update(self) -> None:
        """Tests to update project."""
        url = reverse("projects_v1-detail", kwargs={"pk": 1})
        data = {
            "org": 1,
            "project_name": "Unstract Test",
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
        }
        response = self.client.put(url, data, format="json")
        project_name = response.data["project_name"]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            project_name,
            Project.objects.get(project_name=project_name).project_name,
        )

    def test_projects_update_pk(self) -> None:
        """Tests the PUT method for 400 error."""
        url = reverse("projects_v1-detail", kwargs={"pk": 1})
        data = {
            "org": 2,
            "project_name": "Unstract Test",
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
        }
        response = self.client.put(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_projects_update_field(self) -> None:
        """Tests the PATCH method."""
        url = reverse("projects_v1-detail", kwargs={"pk": 1})
        data = {"project_name": "Unstract Test"}
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        project_name = response.data["project_name"]

        self.assertEqual(
            project_name,
            Project.objects.get(project_name=project_name).project_name,
        )

    def test_projects_delete(self) -> None:
        """Tests the DELETE method."""
        url = reverse("projects_v1-detail", kwargs={"pk": 1})
        response = self.client.delete(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        url = reverse("projects_v1-detail", kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
