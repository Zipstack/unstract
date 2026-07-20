"""E2E: async API execution, whose result only the callback worker can deliver.

With a file to process, COMPLETED is written by exactly one code path — the
chord callback running in the callback worker. The api-deployment worker itself
only ever writes EXECUTING, ERROR, or (with zero files) COMPLETED. So a polled
COMPLETED carrying the per-file result is proof the callback ran and rejoined.
"""

from __future__ import annotations

import io

import pytest

from tests.e2e.api_deployment.conftest import (
    ApiDeployment,
    dispatch_async,
    poll_delivered,
)

pytestmark = [pytest.mark.e2e, pytest.mark.critical]


@pytest.mark.critical_path("callback-result-delivery")
def test_async_execution_result_delivered_by_callback(
    api_deployment: ApiDeployment, llm_mock_response: str
) -> None:
    document = io.BytesIO(b"Async probe. This document is about async widgets.")
    _, status_url = dispatch_async(
        api_deployment, {"files": ("async-probe.txt", document, "text/plain")}
    )

    body = poll_delivered(api_deployment, status_url)
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
