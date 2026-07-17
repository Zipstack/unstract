"""E2E: create a workflow, execute a document through it, poll to COMPLETED.

Covers the app-facing ``/workflow/execute/`` path, distinct from the public
API-deployment endpoint.

Asserts execution status rather than the answer, which a manual execute never
exposes over HTTP; the API-deployment test covers the answer itself. A succeeding
file is proof enough that the mock held: a real completion would fail without a
key.
"""

from __future__ import annotations

import io
import time

import pytest

from tests.e2e.conftest import ProvisionedWorkflow

pytestmark = [pytest.mark.e2e, pytest.mark.critical]

_TERMINAL = {"COMPLETED", "ERROR", "STOPPED"}


@pytest.mark.critical_path("workflow-create-execute")
def test_workflow_execute_completes(
    provisioned_workflow: ProvisionedWorkflow, llm_mock_response: str
) -> None:
    pw = provisioned_workflow
    session = pw.session
    csrf = {"X-CSRFToken": session.cookies.get("csrftoken", "")}

    # Two calls by contract: the first creates a PENDING execution, the second
    # uploads and dispatches it.
    resp = session.post(
        f"{pw.prefix}/workflow/execute/",
        headers=csrf,
        data={"workflow_id": pw.workflow_id},
        timeout=60,
    )
    assert resp.status_code == 200, f"create execution: {resp.text}"
    execution_id = resp.json()["execution_id"]

    document = io.BytesIO(b"Hello invoice 123. This is a test document about widgets.")
    resp = session.post(
        f"{pw.prefix}/workflow/execute/",
        headers=csrf,
        data={"workflow_id": pw.workflow_id, "execution_id": execution_id},
        files={"files": ("probe.txt", document, "text/plain")},
        timeout=120,
    )
    assert resp.status_code == 200, f"dispatch execution: {resp.text}"

    # Not workflow/execution/<pk>/: that route filters by workflow_id and 404s.
    final = {}
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        resp = session.get(f"{pw.prefix}/execution/{execution_id}/", timeout=30)
        resp.raise_for_status()
        final = resp.json()
        if final.get("status") in _TERMINAL:
            break
        time.sleep(2)

    assert final.get("status") == "COMPLETED", final
    assert final.get("successful_files") == 1, final
