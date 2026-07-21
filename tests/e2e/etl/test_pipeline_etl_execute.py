"""E2E: run an ETL pipeline from a source connector to a destination connector.

Distinct from the API paths: nothing is uploaded over HTTP and no result is
returned to the caller. The source connector discovers the file, and the proof
the pipeline ran end to end is the answer landing in the destination store.
"""

from __future__ import annotations

import io
import uuid

import pytest

from tests.e2e.conftest import wait_for_execution
from tests.e2e.etl.conftest import EtlWorkflow, MinioFixture

pytestmark = [pytest.mark.e2e, pytest.mark.critical]

_EXECUTION_TIMEOUT_SECONDS = 300
_DOCUMENT = b"ETL probe. This document is about pipeline widgets and invoices."


@pytest.mark.critical_path("pipeline-etl-execute")
def test_etl_pipeline_writes_answer_to_destination(
    etl_workflow: EtlWorkflow, minio_store: MinioFixture, llm_mock_response: str
) -> None:
    _seed_source_document(etl_workflow, minio_store)

    pipeline_id = _create_pipeline(etl_workflow)
    resp = etl_workflow.session.post(
        f"{etl_workflow.prefix}/pipeline/execute/",
        headers={"X-CSRFToken": etl_workflow.session.cookies.get("csrftoken", "")},
        json={"pipeline_id": pipeline_id},
        timeout=60,
    )
    assert resp.status_code == 200, f"execute pipeline: {resp.text}"
    execution_id = resp.json()["execution"]["execution_id"]

    execution = wait_for_execution(
        etl_workflow.session,
        etl_workflow.prefix,
        execution_id,
        timeout=_EXECUTION_TIMEOUT_SECONDS,
    )
    assert execution.get("status") == "COMPLETED", execution
    assert execution.get("successful_files") == 1, execution

    written = _read_destination_output(minio_store, etl_workflow.output_prefix)
    assert llm_mock_response in written, written[:500]


def _seed_source_document(workflow: EtlWorkflow, store: MinioFixture) -> None:
    """Put the document where the source connector will discover it."""
    store.client.put_object(
        store.bucket,
        f"{workflow.input_prefix}/probe.txt",
        io.BytesIO(_DOCUMENT),
        length=len(_DOCUMENT),
        content_type="text/plain",
    )


def _create_pipeline(workflow: EtlWorkflow) -> str:
    # No cron_string: that would schedule it instead of leaving it on demand.
    resp = workflow.session.post(
        f"{workflow.prefix}/pipeline/",
        headers={"X-CSRFToken": workflow.session.cookies.get("csrftoken", "")},
        # Name is capped at 32 characters.
        json={
            "pipeline_name": f"e2e-etl-{uuid.uuid4().hex[:8]}",
            "workflow": workflow.workflow_id,
            "pipeline_type": "ETL",
        },
        timeout=60,
    )
    assert resp.status_code == 201, f"create pipeline: {resp.text}"
    return resp.json()["id"]


def _read_destination_output(store: MinioFixture, output_prefix: str) -> str:
    """Return the destination object's body, whatever the connector named it."""
    objects = list(
        store.client.list_objects(
            store.bucket, prefix=f"{output_prefix}/", recursive=True
        )
    )
    assert objects, f"nothing written under {output_prefix}/"
    response = store.client.get_object(store.bucket, objects[0].object_name)
    try:
        return response.read().decode("utf-8", errors="replace")
    finally:
        response.close()
        response.release_conn()
