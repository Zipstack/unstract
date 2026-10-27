"""stage_timings exposure in API deployment responses (UN-3451).

The stage breakdown is timing data, so it rides on ``include_metrics`` rather
than widening the default response shape — a caller that never asked for
metrics must see byte-identical metadata to before this change.

Unit tests: ``_enrich_item_workflow_metadata`` is a static method over a
pre-built lookup, so no database is needed.
"""

from unittest.mock import MagicMock

import pytest

from api_v2.deployment_helper import DeploymentHelper

FILE_EXEC_ID = "fe-1"

STAGE_TIMINGS = {
    "version": 1,
    "total": 21.34,
    "stages": {"queue_wait": 1.42, "tool_execution": 18.42},
    "tool_split": {"extraction": 8.92},
}


@pytest.fixture
def fe_lookup():
    """One file execution row carrying a stage breakdown."""
    fe = MagicMock()
    fe.id = FILE_EXEC_ID
    fe.file_name = "invoice.pdf"
    fe.file_hash = "abc"
    fe.execution_time = 21.34
    fe.stage_timings = STAGE_TIMINGS
    fe.workflow_execution = None
    return {FILE_EXEC_ID: fe}


def _enrich(item, fe_lookup, *, include_metrics):
    DeploymentHelper._enrich_item_workflow_metadata(
        item=item,
        file_exec_id=FILE_EXEC_ID,
        fe_lookup=fe_lookup,
        workflow_execution=None,
        organization_id="org-1",
        tag_names=[],
        include_metrics=include_metrics,
    )


def test_included_when_metrics_requested(fe_lookup):
    item = {"file": "invoice.pdf", "file_execution_id": FILE_EXEC_ID}

    _enrich(item, fe_lookup, include_metrics=True)

    assert item["metadata"]["stage_timings"] == STAGE_TIMINGS


def test_omitted_when_metrics_not_requested(fe_lookup):
    item = {"file": "invoice.pdf", "file_execution_id": FILE_EXEC_ID}

    _enrich(item, fe_lookup, include_metrics=False)

    assert "stage_timings" not in item["metadata"]
    # The rest of the metadata is unchanged by this feature.
    assert item["metadata"]["source_name"] == "invoice.pdf"
    assert item["metadata"]["total_elapsed_time"] == 21.34


def test_omitted_when_the_row_has_no_breakdown(fe_lookup):
    """Older rows, Docker tools and duplicate-skipped files have none."""
    fe_lookup[FILE_EXEC_ID].stage_timings = None
    item = {"file": "invoice.pdf", "file_execution_id": FILE_EXEC_ID}

    _enrich(item, fe_lookup, include_metrics=True)

    assert "stage_timings" not in item["metadata"]


def test_value_already_in_metadata_is_not_overwritten(fe_lookup):
    """Enrichment fills gaps; it never clobbers the workers-cache value."""
    cached = {"version": 1, "stages": {"tool_execution": 1.0}}
    item = {
        "file": "invoice.pdf",
        "file_execution_id": FILE_EXEC_ID,
        "metadata": {"stage_timings": cached},
    }

    _enrich(item, fe_lookup, include_metrics=True)

    assert item["metadata"]["stage_timings"] == cached


def test_missing_file_execution_row_is_tolerated():
    item = {"file": "invoice.pdf", "file_execution_id": FILE_EXEC_ID}

    _enrich(item, {}, include_metrics=True)

    assert "stage_timings" not in item["metadata"]
    assert item["metadata"]["organization_id"] == "org-1"
