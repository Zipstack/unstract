"""Fixtures shared by the API-deployment e2e tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
import requests

from tests.e2e.conftest import ProvisionedWorkflow


@dataclass(frozen=True)
class ApiDeployment:
    """A deployed API endpoint and the key that opens it."""

    session: requests.Session
    base: str  # backend root; status_api is returned rooted at it
    prefix: str
    exec_url: str
    api_key: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


@pytest.fixture(scope="session")
def api_deployment(provisioned_workflow: ProvisionedWorkflow) -> ApiDeployment:
    """Deploy the provisioned workflow as an API, once for the whole group."""
    pw = provisioned_workflow
    api_name = f"e2edep{uuid.uuid4().hex[:8]}"
    resp = pw.session.post(
        f"{pw.prefix}/api/deployment/",
        headers={"X-CSRFToken": pw.session.cookies.get("csrftoken", "")},
        json={
            "workflow": pw.workflow_id,
            "display_name": f"e2e {api_name}",
            "description": "e2e api deployment",
            "api_name": api_name,
            "is_active": True,
        },
        timeout=30,
    )
    assert resp.status_code == 201, f"deploy: {resp.text}"
    body = resp.json()
    endpoint = body["api_endpoint"]
    return ApiDeployment(
        session=pw.session,
        base=pw.base,
        prefix=pw.prefix,
        exec_url=(
            endpoint
            if endpoint.startswith("http")
            else f"{pw.base}/{endpoint.lstrip('/')}"
        ),
        api_key=body["api_key"],
    )
