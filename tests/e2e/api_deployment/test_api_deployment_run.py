"""E2E: deploy a workflow as an API, POST a document, get structured JSON back.

Dispatches async and polls the status endpoint for the result: a file-bearing
execution only reaches COMPLETED once the callback rejoins, which the sync POST
cannot reliably wait out under CI load.
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


@pytest.mark.critical_path("api-deployment-run")
@pytest.mark.critical_path("usage-token-tracking")
def test_api_deployment_returns_mocked_answer(
    api_deployment: ApiDeployment, llm_mock_response: str
) -> None:
    document = io.BytesIO(b"Hello invoice 123. This is a test document about widgets.")
    _, status_url = dispatch_async(
        api_deployment, {"files": ("probe.txt", document, "text/plain")}
    )
    body = poll_delivered(api_deployment, status_url, include_metadata=True)
    assert body["status"] == "COMPLETED", body

    file_result = body["message"][0]
    assert file_result["status"] == "Success", file_result
    assert file_result["result"]["output"]["answer"] == llm_mock_response

    # 10/20/30 is litellm's fixed usage for one mocked completion. Counts are
    # summed per reason, so a multiple of it means the prompt made extra calls
    # rather than that tracking is broken.
    usage = file_result["result"]["metadata"]["extraction_llm"][0]
    counts = (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"])
    assert counts == (10, 20, 30), (
        f"expected exactly one mocked extraction call, got {counts} — a multiple "
        f"means the prompt issued more completions than this test assumes: {usage}"
    )
