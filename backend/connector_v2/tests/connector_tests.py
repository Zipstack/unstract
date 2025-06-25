# mypy: ignore-errors
import pytest
from connector_v2.models import ConnectorInstance
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

pytestmark = pytest.mark.django_db


@pytest.mark.connector
class TestConnector(APITestCase):
    def test_connector_list(self) -> None:
        """Tests to List the connectors."""
        url = reverse("connectors_v1-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_connectors_detail(self) -> None:
        """Tests to fetch a connector with given pk."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_connectors_detail_not_found(self) -> None:
        """Tests for negative case to fetch non exiting key."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 768})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_connectors_create(self) -> None:
        """Tests to create a new ConnectorInstance."""
        url = reverse("connectors_v1-list")
        data = {
            "org": 1,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "sample_url",
                "sharable_link": True,
            },
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConnectorInstance.objects.count(), 2)

    def test_connectors_create_with_json_list(self) -> None:
        """Tests to create a new connector with list included in the json
        field.
        """
        url = reverse("connectors_v1-list")
        data = {
            "org": 1,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "sample_url",
                "sharable_link": True,
                "file_name_list": ["a1", "a2"],
            },
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConnectorInstance.objects.count(), 2)

    def test_connectors_create_with_nested_json(self) -> None:
        """Tests to create a new connector with json field as nested json."""
        url = reverse("connectors_v1-list")
        data = {
            "org": 1,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "sample_url",
                "sharable_link": True,
                "sample_metadata_json": {"key1": "value1", "key2": "value2"},
            },
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ConnectorInstance.objects.count(), 2)

    def test_connectors_create_bad_request(self) -> None:
        """Tests for negative case to throw error on a wrong access."""
        url = reverse("connectors_v1-list")
        data = {
            "org": 5,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "sample_url",
                "sharable_link": True,
                "sample_metadata_json": {"key1": "value1", "key2": "value2"},
            },
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_connectors_update_json_field(self) -> None:
        """Tests to update connector with json field update."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        data = {
            "org": 1,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "new_sample_url",
                "sharable_link": True,
                "sample_metadata_json": {"key1": "value1", "key2": "value2"},
            },
        }
        response = self.client.put(url, data, format="json")
        drive_link = response.data["connector_metadata"]["drive_link"]
        self.assertEqual(drive_link, "new_sample_url")

    def test_connectors_update(self) -> None:
        """Tests to update connector update single field."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        data = {
            "org": 1,
            "project": 1,
            "created_by": 1,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "new_sample_url",
                "sharable_link": True,
                "sample_metadata_json": {"key1": "value1", "key2": "value2"},
            },
        }
        response = self.client.put(url, data, format="json")
        modified_by = response.data["modified_by"]
        self.assertEqual(modified_by, 2)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_connectors_update_pk(self) -> None:
        """Tests the PUT method for 400 error."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        data = {
            "org": 2,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "new_sample_url",
                "sharable_link": True,
                "sample_metadata_json": {"key1": "value1", "key2": "value2"},
            },
        }
        response = self.client.put(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_connectors_update_json_fields(self) -> None:
        """Tests to update ConnectorInstance."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        data = {
            "org": 1,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "new_sample_url",
                "sharable_link": True,
                "sample_metadata_json": {"key1": "value1", "key2": "value2"},
            },
        }
        response = self.client.put(url, data, format="json")
        nested_value = response.data["connector_metadata"]["sample_metadata_json"]["key1"]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(nested_value, "value1")

    def test_connectors_update_json_list_fields(self) -> None:
        """Tests to update connector to the third second level of json."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        data = {
            "org": 1,
            "project": 1,
            "created_by": 2,
            "modified_by": 2,
            "modified_at": "2023-06-14T05:28:47.759Z",
            "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
            "connector_metadata": {
                "drive_link": "new_sample_url",
                "sharable_link": True,
                "sample_metadata_json": {"key1": "value1", "key2": "value2"},
                "file_list": ["a1", "a2", "a3"],
            },
        }
        response = self.client.put(url, data, format="json")
        nested_value = response.data["connector_metadata"]["sample_metadata_json"]["key1"]
        nested_list = response.data["connector_metadata"]["file_list"]
        last_val = nested_list.pop()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(nested_value, "value1")
        self.assertEqual(last_val, "a3")

    # @pytest.mark.xfail(raises=KeyError)
    # def test_connectors_update_json_fields_failed(self) -> None:
    #     """Tests to update connector to the second level of JSON with a wrong
    #     key."""

    #     url = reverse("connectors_v1-detail", kwargs={"pk": 1})
    #     data = {
    #         "org": 1,
    #         "project": 1,
    #         "created_by": 2,
    #         "modified_by": 2,
    #         "modified_at": "2023-06-14T05:28:47.759Z",
    #         "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
    #         "connector_metadata": {
    #             "drive_link": "new_sample_url",
    #             "sharable_link": True,
    #             "sample_metadata_json": {"key1": "value1", "key2": "value2"},
    #         },
    #     }
    #     response = self.client.put(url, data, format="json")
    #     nested_value = response.data["connector_metadata"]["sample_metadata_json"][
    #         "key00"
    #     ]

    # @pytest.mark.xfail(raises=KeyError)
    # def test_connectors_update_json_nested_failed(self) -> None:
    #     """Tests to update connector to test a first level of json with a wrong
    #     key."""

    #     url = reverse("connectors_v1-detail", kwargs={"pk": 1})
    #     data = {
    #         "org": 1,
    #         "project": 1,
    #         "created_by": 2,
    #         "modified_by": 2,
    #         "modified_at": "2023-06-14T05:28:47.759Z",
    #         "connector_id": "e3a4512m-efgb-48d5-98a9-3983nd77f",
    #         "connector_metadata": {
    #             "drive_link": "new_sample_url",
    #             "sharable_link": True,
    #             "sample_metadata_json": {"key1": "value1", "key2": "value2"},
    #         },
    #     }
    #     response = self.client.put(url, data, format="json")
    #     nested_value = response.data["connector_metadata"]["sample_metadata_jsonNew"]

    def test_connectors_update_field(self) -> None:
        """Tests the PATCH method."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        data = {"connector_id": "e3a4512m-efgb-48d5-98a9-3983ntest"}
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        connector_id = response.data["connector_id"]

        self.assertEqual(
            connector_id,
            ConnectorInstance.objects.get(connector_id=connector_id).connector_id,
        )

    def test_connectors_update_json_field_patch(self) -> None:
        """Tests the PATCH method."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        data = {
            "connector_metadata": {
                "drive_link": "patch_update_url",
                "sharable_link": True,
                "sample_metadata_json": {
                    "key1": "patch_update1",
                    "key2": "value2",
                },
            }
        }

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        drive_link = response.data["connector_metadata"]["drive_link"]

        self.assertEqual(drive_link, "patch_update_url")

    def test_connectors_delete(self) -> None:
        """Tests the DELETE method."""
        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        response = self.client.delete(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        url = reverse("connectors_v1-detail", kwargs={"pk": 1})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
