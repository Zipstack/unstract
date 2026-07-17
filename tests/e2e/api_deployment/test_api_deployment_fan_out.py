"""E2E: a multi-file execution fans out to file-processing workers and rejoins.

Fan-out only happens when the backend hands out MAX_PARALLEL_FILE_BATCHES > 1
(the test overlay sets it); at the default of 1 every file lands in a single
batch and this would pass while proving nothing. The rejoin is the chord
callback: one result per file, and per-file rows counted back up into
successful_files.
"""

from __future__ import annotations

import io

import pytest

from tests.e2e.api_deployment.conftest import ApiDeployment

pytestmark = [pytest.mark.e2e, pytest.mark.critical]

# One file per batch, matching the overlay's MAX_PARALLEL_FILE_BATCHES.
_DOCUMENTS = {
    "fan-alpha.txt": b"Alpha document. This one is about alpha widgets and invoices.",
    "fan-beta.txt": b"Beta document. A different text about beta gadgets entirely.",
    "fan-gamma.txt": b"Gamma document. Yet another distinct body concerning gamma.",
}


@pytest.mark.critical_path("workflow-execution-fan-out")
def test_multi_file_execution_fans_out_and_rejoins(
    api_deployment: ApiDeployment, llm_mock_response: str
) -> None:
    # Bodies must differ: identical files are deduplicated by hash on ingest and
    # would come back as fewer results, which reads as a lost file.
    files = [
        ("files", (name, io.BytesIO(body), "text/plain"))
        for name, body in _DOCUMENTS.items()
    ]
    resp = api_deployment.session.post(
        api_deployment.exec_url,
        headers=api_deployment.auth,
        data={"timeout": 300, "include_metadata": False},
        files=files,
        timeout=310,
    )
    assert resp.status_code == 200, f"execute: HTTP {resp.status_code}: {resp.text}"
    message = resp.json()["message"]
    assert message["execution_status"] == "COMPLETED", message

    # Keyed by name, not position: batches rejoin in completion order.
    by_name = {entry["file"]: entry for entry in message["result"]}
    assert sorted(by_name) == sorted(_DOCUMENTS), message["result"]
    for name, entry in by_name.items():
        assert entry["status"] == "Success", (name, entry)
        assert entry["result"]["output"]["answer"] == llm_mock_response, (name, entry)

    execution_id = message["execution_id"]
    _assert_totals_rejoined(api_deployment, execution_id)
    _assert_recorded_per_file(api_deployment, execution_id)


def _assert_totals_rejoined(deployment: ApiDeployment, execution_id: str) -> None:
    """Every fanned-out file is counted back into the execution's totals."""
    resp = deployment.session.get(
        f"{deployment.prefix}/execution/{execution_id}/", timeout=30
    )
    resp.raise_for_status()
    execution = resp.json()
    assert execution["total_files"] == len(_DOCUMENTS), execution
    # Counted from the per-file rows the fanned-out workers wrote, so this is
    # the rejoin itself rather than a status the dispatcher could set alone.
    assert execution["successful_files"] == len(_DOCUMENTS), execution
    assert execution["failed_files"] == 0, execution


def _assert_recorded_per_file(deployment: ApiDeployment, execution_id: str) -> None:
    """The fan-out granularity is visible per file, not only in the totals."""
    resp = deployment.session.get(
        f"{deployment.prefix}/execution/{execution_id}/files/", timeout=30
    )
    resp.raise_for_status()
    body = resp.json()
    rows = body if isinstance(body, list) else body.get("results", [])
    assert len(rows) == len(_DOCUMENTS), rows
