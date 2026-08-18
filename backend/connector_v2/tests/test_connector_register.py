"""Critical path ``connector-register-test``: credentials are validated against
the live external system, and a registered connector persists them encrypted.

``POST /test_connectors/`` is the only place the platform proves it can actually
reach a customer's storage before a workflow depends on it; a version that
always answers "valid" would surface as a run-time failure deep inside an
execution. Runs against the rig's MinIO. Needs a live DB (integration tier).
"""

from __future__ import annotations

import os
import secrets

import pytest
from account_v2.models import Organization, User
from django.db import connection
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from connector_v2.models import ConnectorInstance

MINIO_CONNECTOR_ID = "minio|c799f6e3-2b57-434e-aaac-b5daa415da19"

pytestmark = pytest.mark.skipif(
    not all(
        os.environ.get(var)
        for var in (
            "MINIO_ACCESS_KEY_ID",
            "MINIO_SECRET_ACCESS_KEY",
            "MINIO_ENDPOINT_URL",
        )
    ),
    reason="needs a live MinIO (provisioned by the rig for this group)",
)


def _credentials(secret: str | None = None) -> dict:
    return {
        "connectorName": "rig-minio",
        "key": os.environ["MINIO_ACCESS_KEY_ID"],
        "secret": secret or os.environ["MINIO_SECRET_ACCESS_KEY"],
        "endpoint_url": os.environ["MINIO_ENDPOINT_URL"],
        "region_name": "",
        "path": "/",
    }


class ConnectorRegisterTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-conn", display_name="Org Conn", organization_id="org-conn"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.user = User.objects.create_user(
            username="connector@example.com",
            email="connector@example.com",
            password=secrets.token_urlsafe(),
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.user, role="user"
        )
        self.factory = APIRequestFactory()

    def _test_connector(self, credentials: dict):
        from connector_processor.views import ConnectorViewSet

        view = ConnectorViewSet.as_view({"post": "test"})
        request = self.factory.post(
            "/api/v1/test_connectors/",
            {"connector_id": MINIO_CONNECTOR_ID, "connector_metadata": credentials},
            format="json",
        )
        force_authenticate(request, user=self.user)
        return view(request)

    @pytest.mark.critical_path("connector-register-test")
    def test_good_credentials_validate_bad_ones_do_not(self) -> None:
        valid = self._test_connector(_credentials())
        assert valid.status_code == status.HTTP_200_OK, valid.data
        assert valid.data["is_valid"] is True

        invalid = self._test_connector(_credentials(secret="wrong-secret"))
        assert invalid.status_code >= status.HTTP_400_BAD_REQUEST, invalid.data
        assert "is_valid" not in invalid.data

    @pytest.mark.critical_path("connector-register-test")
    def test_register_persists_credentials_encrypted(self) -> None:
        from connector_v2.views import ConnectorInstanceViewSet

        view = ConnectorInstanceViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/api/v1/connector/",
            {
                "connector_id": MINIO_CONNECTOR_ID,
                "connector_name": "rig-minio",
                "connector_metadata": _credentials(),
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = view(request)

        assert response.status_code == status.HTTP_201_CREATED, response.data
        instance = ConnectorInstance.objects.get(id=response.data["id"])
        assert instance.organization_id == self.org.id
        # Decrypts back to the input on read...
        assert instance.connector_metadata["key"] == os.environ["MINIO_ACCESS_KEY_ID"]

        # ...but the raw column must be ciphertext. Read it past the field's
        # decrypting descriptor, else a regression to plaintext still passes.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT connector_metadata FROM connector_instance WHERE id = %s",
                [str(instance.id)],
            )
            raw = bytes(cursor.fetchone()[0])
        secret = os.environ["MINIO_SECRET_ACCESS_KEY"].encode()
        assert secret not in raw
        assert os.environ["MINIO_ACCESS_KEY_ID"].encode() not in raw
