"""Fixtures shared by the API-deployment e2e tests."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from tests.e2e.conftest import ProvisionedWorkflow

# A file-bearing execution reaches COMPLETED only once the chord callback
# rejoins, which the synchronous POST cannot wait out reliably under load. Every
# api-deployment test therefore dispatches async (timeout=0) and polls the
# status endpoint — the one path the codebase itself proves works.
# Per-test budget. Three tests in this group share one 600s group timeout, so
# this stays well under a third of it to leave room for provisioning.
_POLL_TIMEOUT_SECONDS = 150
# A slow poll response is not a verdict on the execution — keep waiting rather
# than failing the test on a transient blip.
_TRANSIENT = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)


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


def dispatch_async(
    deployment: ApiDeployment,
    files: list | dict,
    **form: object,
) -> tuple[str, str]:
    """POST an async execution (timeout=0) and return (execution_id, status_url).

    Leaves the result for the callback to deliver; asserts the immediate PENDING
    handshake so a caller only ever polls a genuinely dispatched execution.
    """
    resp = deployment.session.post(
        deployment.exec_url,
        headers=deployment.auth,
        data={"timeout": 0, **form},
        files=files,
        timeout=60,
    )
    assert resp.status_code == 200, f"dispatch: HTTP {resp.status_code}: {resp.text}"
    message = resp.json()["message"]
    assert message["execution_status"] == "PENDING", message
    assert message["result"] is None, message
    # The async PENDING body carries the execution id only inside status_api's
    # query string, not as a top-level field.
    status_api = message["status_api"]
    assert status_api, message
    status_url = f"{deployment.base}/{status_api.lstrip('/')}"
    execution_id = parse_qs(urlparse(status_api).query).get("execution_id", [None])[0]
    assert execution_id, message
    return execution_id, status_url


def poll_delivered(
    deployment: ApiDeployment, status_url: str, *, include_metadata: bool = False
) -> dict:
    """Poll until the result is delivered (HTTP 200), tolerating not-ready blips.

    The status endpoint answers 422 both while running and after a failure, so
    the body is read to tell them apart rather than spinning until the timeout on
    an execution that already gave up. The read is destructive: the first 200
    acknowledges the result, so call this once per execution.
    """
    params = {"include_metadata": str(include_metadata).lower()}
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    last = ""
    while time.monotonic() < deadline:
        try:
            resp = deployment.session.get(
                status_url, headers=deployment.auth, params=params, timeout=30
            )
        except _TRANSIENT as exc:
            last = repr(exc)
            time.sleep(2)
            continue
        last = resp.text
        if resp.status_code == 200:
            return resp.json()
        # 406 means the result was already acknowledged and cleared — a prior
        # 200 was lost in transit, so the body is gone and cannot be recovered.
        if resp.status_code == 406:
            pytest.fail(f"result already acknowledged (200 lost in transit): {last}")
        # 422 is the only "still running / failed" answer; anything else is a
        # real error the view surfaced (400/500/…), not a poll-protocol hiccup.
        if resp.status_code != 422:
            pytest.fail(f"unexpected poll status HTTP {resp.status_code}: {last}")
        status = _status_of(resp)
        assert status, f"422 body carried no status (contract change?): {last}"
        assert status not in ("ERROR", "STOPPED"), f"execution failed: {last}"
        time.sleep(2)
    pytest.fail(f"result never delivered within {_POLL_TIMEOUT_SECONDS}s; last: {last}")


def _status_of(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("status", ""))
    except ValueError:  # a non-JSON body has no status; the caller asserts on it
        return ""


@pytest.fixture(scope="session")
def api_deployment(provisioned_workflow: ProvisionedWorkflow) -> ApiDeployment:
    """Deploy the provisioned workflow as an API.

    Session-scoped, so it runs once per xdist worker (not once per group) when
    the group is parallelised.
    """
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
