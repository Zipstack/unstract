"""E2E: a multi-file execution rejoins after being dispatched to workers.

The rejoin is the chord callback: one result per file, and per-file rows counted
back up into successful_files. That half is directly observable.

The fan-out half is NOT asserted here, and the critical path is recorded as a
gap. Nothing persists a batch or task id, so the only available proxy was
per-file timing, and timing cannot decide it: on a loaded CI runner three files
genuinely running in parallel finish further apart than three run serially,
because the contention they create outweighs the overlap they gain. Closing the
gap needs batch identity on the row, not a better statistic.
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

# One file per batch, matching the overlay's MAX_PARALLEL_FILE_BATCHES.
_DOCUMENTS = {
    "fan-alpha.txt": b"Alpha document. This one is about alpha widgets and invoices.",
    "fan-beta.txt": b"Beta document. A different text about beta gadgets entirely.",
    "fan-gamma.txt": b"Gamma document. Yet another distinct body concerning gamma.",
}


def test_multi_file_execution_rejoins(
    api_deployment: ApiDeployment, llm_mock_response: str
) -> None:
    # Bodies must differ: identical files are deduplicated by hash on ingest and
    # would come back as fewer results, which reads as a lost file.
    files = [
        ("files", (name, io.BytesIO(body), "text/plain"))
        for name, body in _DOCUMENTS.items()
    ]
    execution_id, status_url = dispatch_async(api_deployment, files)
    body = poll_delivered(api_deployment, status_url)
    assert body["status"] == "COMPLETED", body

    # Keyed by name, not position: batches rejoin in completion order.
    by_name = {entry["file"]: entry for entry in body["message"]}
    assert sorted(by_name) == sorted(_DOCUMENTS), body["message"]
    for name, entry in by_name.items():
        assert entry["status"] == "Success", (name, entry)
        assert entry["result"]["output"]["answer"] == llm_mock_response, (name, entry)

    _assert_totals_rejoined(api_deployment, execution_id)
    rows = _fetch_file_rows(api_deployment, execution_id)
    assert len(rows) == len(_DOCUMENTS), rows


def _assert_totals_rejoined(deployment: ApiDeployment, execution_id: str) -> None:
    """Every file is counted back into the execution's totals."""
    resp = deployment.session.get(
        f"{deployment.prefix}/execution/{execution_id}/", timeout=30
    )
    resp.raise_for_status()
    execution = resp.json()
    assert execution["total_files"] == len(_DOCUMENTS), execution
    # Counted from the per-file rows the workers wrote, so this is the rejoin
    # itself rather than a status the dispatcher could set alone.
    assert execution["successful_files"] == len(_DOCUMENTS), execution
    assert execution["failed_files"] == 0, execution


def _fetch_file_rows(deployment: ApiDeployment, execution_id: str) -> list[dict]:
    """The per-file rows, which exist only because the workers wrote them."""
    resp = deployment.session.get(
        f"{deployment.prefix}/execution/{execution_id}/files/", timeout=30
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else body.get("results", [])
