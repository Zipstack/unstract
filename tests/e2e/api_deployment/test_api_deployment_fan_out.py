"""E2E: a multi-file execution fans out to file-processing workers and rejoins.

The rejoin is the chord callback: one result per file, and per-file rows counted
back up into successful_files.

Proving the fan-out half needs care, because nothing records a batch or task id
— see `_assert_files_ran_concurrently` for the timing argument that stands in
for it, and why the obvious alternatives don't discriminate.
"""

from __future__ import annotations

import io
from datetime import datetime

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


@pytest.mark.critical_path("workflow-execution-fan-out")
def test_multi_file_execution_fans_out_and_rejoins(
    api_deployment: ApiDeployment, llm_mock_response: str, llm_mock_delay: float
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
    _assert_files_ran_concurrently(rows, llm_mock_delay)


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


def _assert_files_ran_concurrently(rows: list[dict], delay: float) -> None:
    """Each file's own clock covers only its own work, so the batches overlapped.

    Every completion stalls for `delay`, and a row's window opens when the worker
    that owns its batch picks the batch up. Serialised in one batch, all rows
    open together and each successive file's window has to swallow the ones
    before it -- roughly delay, 2*delay, 3*delay. Fanned out, each row opens with
    its own batch, so every window is about one delay wide.

    Comparing durations rather than overlap is deliberate: serialised rows are
    created in one tight loop, so their windows overlap too and an overlap test
    would pass on exactly the case it must catch.
    """
    windows = [
        (_parse(row["created_at"]), _parse(row["modified_at"])) for row in rows
    ]
    durations = sorted((end - start).total_seconds() for start, end in windows)
    # The two outcomes predict a spread of ~0 (fanned out) or ~2*delay (the last
    # file waiting on the two before it), so one delay is the midpoint between
    # them. Anything tighter would be measuring runner contention, not batching.
    assert durations[-1] - durations[0] < delay, (
        f"per-file durations {durations} spread by more than {delay}s, closer to "
        f"the {2 * delay}s of serialising the files into one batch than to fan-out"
    )
    # Guards the guard: without the stall taking effect the spread is ~0 either
    # way, and the assertion above would hold for a serial run too.
    assert durations[0] >= delay, (
        f"per-file durations {durations} are below the {delay}s mock delay — "
        "the workers never applied it, so this proves nothing about fan-out"
    )


def _parse(timestamp: str) -> datetime:
    # Django serialises UTC as a trailing Z, which fromisoformat rejects
    # before 3.11.
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
