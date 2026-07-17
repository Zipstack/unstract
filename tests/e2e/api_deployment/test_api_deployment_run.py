"""E2E: deploy a workflow as an API, POST a document, get structured JSON back.

Runs synchronously (a non-zero timeout blocks) so the result arrives on the POST
itself, leaving no polling or out-of-band result store to read.
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
