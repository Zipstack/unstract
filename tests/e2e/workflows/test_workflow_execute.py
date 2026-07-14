"""E2E: create a workflow, execute a document through it, poll to COMPLETED.

Exercises the app-facing ``/workflow/execute/`` path (distinct from the public
API-deployment endpoint). The LLM is mocked via UNSTRACT_LLM_MOCK_RESPONSE, so a
COMPLETED status with a successful file is itself the hermetic proof: without a
real key the completion would fail and the file would not succeed.

The per-file answer is not exposed over HTTP for a manual execute (it lands in a
worker-side result store), so this asserts on the execution status the status
endpoint does expose. The exact mocked answer is asserted by the API-deployment
test, whose endpoint returns it as JSON.
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

    # Two-step contract: call 1 (no files) creates a PENDING execution without
    # dispatching; call 2 (with that execution_id + files) uploads and dispatches.
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

    # Poll the top-level execution app (retrieve by execution_id). The
    # workflow/execution/<pk>/ route filters by workflow_id and 404s here.
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
