"""E2E: deploy a workflow as an API, POST a document, get structured JSON back.

Covers two critical paths in one hermetic run (the LLM is mocked via
UNSTRACT_LLM_MOCK_RESPONSE, so no real provider/secret is touched):

  • api-deployment-run   — the public deployment endpoint executes and returns
                           the mocked answer as structured JSON.
  • usage-token-tracking — per-execution token usage is recorded and returned
                           (litellm stamps a fixed 10/20/30 on the mock).

Synchronous execution (timeout > 0 blocks) so the result comes back on the POST
itself — no polling and no out-of-band result store to read.
"""

from __future__ import annotations

import io
import uuid

import pytest

from tests.e2e.conftest import ProvisionedWorkflow

pytestmark = [pytest.mark.e2e, pytest.mark.critical]


@pytest.mark.critical_path("api-deployment-run")
@pytest.mark.critical_path("usage-token-tracking")
def test_api_deployment_returns_mocked_answer(
    provisioned_workflow: ProvisionedWorkflow, llm_mock_response: str
) -> None:
    pw = provisioned_workflow
    session = pw.session
    csrf = {"X-CSRFToken": session.cookies.get("csrftoken", "")}

    api_name = f"e2edep{uuid.uuid4().hex[:8]}"
    resp = session.post(
        f"{pw.prefix}/api/deployment/",
        headers=csrf,
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
    deployment = resp.json()
    api_key = deployment["api_key"]
    endpoint = deployment["api_endpoint"]
    exec_url = endpoint if endpoint.startswith("http") else f"{pw.base}/{endpoint.lstrip('/')}"

    document = io.BytesIO(b"Hello invoice 123. This is a test document about widgets.")
    resp = session.post(
        exec_url,
        headers={"Authorization": f"Bearer {api_key}"},
        data={"timeout": 300, "include_metadata": True},
        files={"files": ("probe.txt", document, "text/plain")},
        timeout=310,
    )
    assert resp.status_code == 200, f"execute: HTTP {resp.status_code}: {resp.text}"
    message = resp.json()["message"]
    assert message["execution_status"] == "COMPLETED", message

    file_result = message["result"][0]
    assert file_result["status"] == "Success", file_result
    # api-deployment-run: the mocked completion surfaces as the prompt's answer.
    assert file_result["result"]["output"]["answer"] == llm_mock_response

    # usage-token-tracking: litellm stamps a deterministic 10/20/30 on the mock,
    # recorded per-execution and returned under the file's metadata.
    usage = file_result["result"]["metadata"]["extraction_llm"][0]
    assert usage["input_tokens"] == 10, usage
    assert usage["output_tokens"] == 20, usage
    assert usage["total_tokens"] == 30, usage
