"""E2E: deploy a workflow as an API, POST a document, get structured JSON back.

Runs synchronously (a non-zero timeout blocks) so the result arrives on the POST
itself, leaving no polling or out-of-band result store to read.
"""

from __future__ import annotations

import io

import pytest

from tests.e2e.api_deployment.conftest import ApiDeployment

pytestmark = [pytest.mark.e2e, pytest.mark.critical]


@pytest.mark.critical_path("api-deployment-run")
@pytest.mark.critical_path("usage-token-tracking")
def test_api_deployment_returns_mocked_answer(
    api_deployment: ApiDeployment, llm_mock_response: str
) -> None:
    document = io.BytesIO(b"Hello invoice 123. This is a test document about widgets.")
    resp = api_deployment.session.post(
        api_deployment.exec_url,
        headers=api_deployment.auth,
        data={"timeout": 300, "include_metadata": True},
        files={"files": ("probe.txt", document, "text/plain")},
        timeout=310,
    )
    assert resp.status_code == 200, f"execute: HTTP {resp.status_code}: {resp.text}"
    message = resp.json()["message"]
    assert message["execution_status"] == "COMPLETED", message

    file_result = message["result"][0]
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
