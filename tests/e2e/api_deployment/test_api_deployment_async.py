"""E2E: async API execution, whose result only the callback worker can deliver.

With a file to process, COMPLETED is written by exactly one code path — the
chord callback running in the callback worker. The api-deployment worker itself
only ever writes EXECUTING, ERROR, or (with zero files) COMPLETED. So a polled
COMPLETED carrying the per-file result is proof the callback ran and rejoined.
"""

from __future__ import annotations

import io
import time

import pytest
import requests

from tests.e2e.api_deployment.conftest import ApiDeployment

pytestmark = [pytest.mark.e2e, pytest.mark.critical]

_POLL_TIMEOUT_SECONDS = 300


@pytest.mark.critical_path("callback-result-delivery")
def test_async_execution_result_delivered_by_callback(
    api_deployment: ApiDeployment, llm_mock_response: str
) -> None:
    document = io.BytesIO(b"Async probe. This document is about async widgets.")
    resp = api_deployment.session.post(
        api_deployment.exec_url,
        headers=api_deployment.auth,
        # timeout=0 returns without waiting, leaving the result for the callback.
        data={"timeout": 0, "include_metadata": False},
        files={"files": ("async-probe.txt", document, "text/plain")},
        timeout=60,
    )
    assert resp.status_code == 200, f"dispatch: HTTP {resp.status_code}: {resp.text}"
    message = resp.json()["message"]
    assert message["execution_status"] == "PENDING", message
    assert message["result"] is None, message

    status_api = message["status_api"]
    assert status_api, message
    status_url = f"{api_deployment.base}/{status_api.lstrip('/')}"

    body = _poll_until_delivered(api_deployment, status_url)
    assert body["status"] == "COMPLETED", body

    file_result = body["message"][0]
    assert file_result["status"] == "Success", file_result
    assert file_result["result"]["output"]["answer"] == llm_mock_response

    # The read is destructive: fetching a delivered result acknowledges it, and
    # acknowledged results are gone. Pinning it stops a retry loop from being
    # added later that would silently swallow the only copy.
    again = api_deployment.session.get(
        status_url, headers=api_deployment.auth, timeout=30
    )
    assert again.status_code == 406, f"expected acknowledged, got {again.text}"


def _poll_until_delivered(deployment: ApiDeployment, status_url: str) -> dict:
    """Poll until the result is delivered, tolerating not-ready responses.

    The status endpoint answers 422 both while the execution is still running
    and once it has failed, so this reads the body to tell them apart rather
    than spinning until the timeout on an execution that already gave up.
    """
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    last = ""
    while time.monotonic() < deadline:
        resp = deployment.session.get(status_url, headers=deployment.auth, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        assert resp.status_code == 422, f"poll: HTTP {resp.status_code}: {resp.text}"
        last = resp.text
        assert _status_of(resp) not in ("ERROR", "STOPPED"), f"execution failed: {last}"
        time.sleep(2)
    pytest.fail(f"result never delivered within {_POLL_TIMEOUT_SECONDS}s; last: {last}")


def _status_of(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("status", ""))
    except ValueError:  # a non-JSON error body is not a terminal verdict
        return ""
