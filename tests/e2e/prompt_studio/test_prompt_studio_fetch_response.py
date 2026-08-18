"""E2E: run a single prompt inside Prompt Studio and read its response back.

This is the authoring surface, not workflow execution: the answer is produced by
the executor worker (so the LLM mock applies) and written back asynchronously by
the IDE callback worker, which is why the output is polled rather than returned.
"""

from __future__ import annotations

import io
import time

import pytest
import requests

from tests.e2e.conftest import ProvisionedWorkflow

pytestmark = [pytest.mark.e2e, pytest.mark.critical]

_OUTPUT_TIMEOUT_SECONDS = 240

# Upload sniffs content rather than trusting the declared type, and OSS accepts
# only PDF — so this has to be a real one, however empty.
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
    b"%%EOF\n"
)


@pytest.mark.critical_path("prompt-studio-fetch-response")
def test_fetch_response_returns_mocked_answer(
    provisioned_workflow: ProvisionedWorkflow, llm_mock_response: str
) -> None:
    pw = provisioned_workflow
    document_id = _upload_document(pw)

    resp = _post(
        pw,
        f"{pw.prefix}/prompt-studio/fetch_response/{pw.tool_id}",
        json={
            "id": pw.prompt_id,
            "document_id": document_id,
            "profile_manager": pw.profile_id,
        },
    )
    # Accepted, not answered: the run is dispatched and written back later.
    assert resp.status_code == 202, f"fetch_response: {resp.text}"

    output = _poll_for_output(pw, document_id)
    assert output == llm_mock_response, output


def _upload_document(pw: ProvisionedWorkflow) -> str:
    resp = pw.session.post(
        f"{pw.prefix}/prompt-studio/file/{pw.tool_id}",
        headers={"X-CSRFToken": pw.session.cookies.get("csrftoken", "")},
        files={"file": ("probe.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
        timeout=60,
    )
    assert resp.status_code == 200, f"upload: {resp.text}"
    return resp.json()["data"][0]["document_id"]


def _poll_for_output(pw: ProvisionedWorkflow, document_id: str) -> str | None:
    """Wait for the answer to be written back, then return it.

    Polls the output itself rather than the task status: the task completing and
    the callback having stored its result are different moments, and the status
    reports only the first.
    """
    deadline = time.monotonic() + _OUTPUT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        rows = _prompt_outputs(pw, document_id)
        for row in rows:
            if row.get("output") is not None:
                return row["output"]
        time.sleep(2)
    pytest.fail(f"no prompt output within {_OUTPUT_TIMEOUT_SECONDS}s")


def _prompt_outputs(pw: ProvisionedWorkflow, document_id: str) -> list[dict]:
    resp = pw.session.get(
        f"{pw.prefix}/prompt-studio/prompt-output/",
        params={
            "tool_id": pw.tool_id,
            "document_manager": document_id,
            "prompt_id": pw.prompt_id,
            "is_single_pass_extract": "false",
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else body.get("results", [])


def _post(pw: ProvisionedWorkflow, url: str, **kwargs: object) -> requests.Response:
    headers = {"X-CSRFToken": pw.session.cookies.get("csrftoken", "")}
    return pw.session.post(url, headers=headers, timeout=60, **kwargs)
