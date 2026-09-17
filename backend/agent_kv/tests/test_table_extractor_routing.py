"""Routing a `table` extractor entry to the table executor.

The wire format is extractor-scoped (§7.0): `extractors: [{name, keys, options}]`.
v1 accepts exactly one entry, but WHICH one is now a choice, so the job row has
to record it -- status and result used to key everything under the hardcoded
`kv` name, which would have filed a table job's output under the wrong
extractor.
"""

import json
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv import dispatch  # noqa: E402
from agent_kv.constants import (  # noqa: E402
    EXTRACTOR_ROUTES,
    STAGE_NAMES_BY_EXTRACTOR,
    TABLE_EXTRACTOR_NAME,
    V1_EXTRACTOR_NAME,
)
from agent_kv.execution_serializers import (  # noqa: E402
    SUPPORTED_EXTRACTORS,
    ExtractorSerializer,
)
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def test_both_extractors_are_supported():
    assert set(SUPPORTED_EXTRACTORS) == {V1_EXTRACTOR_NAME, TABLE_EXTRACTOR_NAME}


def test_every_supported_extractor_has_a_route_and_a_stage_list():
    """A supported extractor with no route dispatches nowhere; with no stage
    list its progress is recorded and then filtered out of the status document.
    """
    for name in SUPPORTED_EXTRACTORS:
        assert name in EXTRACTOR_ROUTES, name
        assert name in STAGE_NAMES_BY_EXTRACTOR, name


def test_the_table_route_targets_the_existing_executor():
    """R1: the queue is derived from the executor name, and
    celery_executor_agentic_table is already wired. A new executor name here
    would be accepted, dispatch silently, and never drain.
    """
    executor, operation = EXTRACTOR_ROUTES[TABLE_EXTRACTOR_NAME]
    assert executor == "agentic_table"
    assert operation == "table_extract_api"


def test_a_table_entry_validates_with_its_own_options():
    data = {
        "name": "table",
        "keys": {"target_table": "Rent rolls"},
        "options": {"instructions": "skip totals rows"},
    }
    s = ExtractorSerializer(data=data)
    assert s.is_valid(), s.errors
    assert s.validated_data["options"]["instructions"] == "skip totals rows"


def test_a_table_entry_requires_a_target_table():
    s = ExtractorSerializer(data={"name": "table", "keys": {}, "options": {}})
    assert not s.is_valid()
    assert "target_table" in json.dumps(s.errors)


def test_kv_options_are_rejected_on_a_table_entry():
    """The whole point of per-extractor options: an option aimed at the wrong
    extractor must not be silently dropped.
    """
    s = ExtractorSerializer(
        data={"name": "table", "keys": {"target_table": "T"}, "options": {"qa": True}}
    )
    assert not s.is_valid()
    assert "qa" in json.dumps(s.errors)


def test_table_options_are_rejected_on_a_kv_entry():
    s = ExtractorSerializer(
        data={
            "name": "kv",
            # A schema valid under kv_schema's own leaf-attribute allowlist --
            # this test is about options being extractor-scoped, not about
            # `keys` validation, so `keys` itself must not fail here (a `keys`
            # error would short-circuit DRF's to_internal_value() before the
            # object-level validate() that scopes `options` ever runs).
            "keys": {"total": {"description": "d"}},
            "options": {"target_table": "Rent rolls"},
        }
    )
    assert not s.is_valid()
    assert "target_table" in json.dumps(s.errors)


def _job(extractor=TABLE_EXTRACTOR_NAME, **overrides):
    """An unsaved job with an unsaved org -- this suite's established pattern.

    `test_dispatch.py` builds jobs exactly this way and the whole `agent_kv`
    suite touches no database (there is no `django_db` marker anywhere in it).
    Assigning an unsaved `Organization` with an explicit PK caches it on the
    job, so `job.organization` never hits the DB, and the slug is deliberately
    different from the PK so a test can tell which one the code reached for.
    """
    from account_v2.models import Organization

    job = AgentKVJob(id=uuid.uuid4(), input_ref="org/o/agent_kv/j/input.pdf")
    job.organization = Organization(id=7, organization_id="org_slug_1")
    job.extractor = extractor
    job.pages_total = 3
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_dispatch_uses_the_route_for_the_requested_extractor(m_objects, m_disp, m_key):
    job = _job()
    dispatch.dispatch_job(
        job,
        extractor=TABLE_EXTRACTOR_NAME,
        schema={"target_table": "Rent rolls"},
        options={"page_start": 1, "page_end": None},
    )

    ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
    assert ctx.executor_name == "agentic_table"
    assert ctx.operation == "table_extract_api"
    # The executor_params shape does NOT branch by extractor -- both executors
    # read the same keys, which is what lets one dispatcher serve both.
    assert ctx.executor_params["schema"] == {"target_table": "Rent rolls"}
    assert ctx.executor_params["input_ref"] == job.input_ref
    assert ctx.executor_params["platform_api_key"] == "pk"


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "objects")
def test_the_kv_route_is_unchanged(m_objects, m_disp, m_key):
    """Regression: making the route a lookup must not move the kv extractor."""
    job = _job(extractor=V1_EXTRACTOR_NAME)
    dispatch.dispatch_job(
        job,
        extractor=V1_EXTRACTOR_NAME,
        schema={"a": {"description": "d"}},
        options={"qa": True},
    )
    ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
    assert ctx.executor_name == "agentic_kv"
    assert ctx.operation == "kv_extract"


def test_the_status_document_keys_stages_by_the_extractor_that_ran():
    from agent_kv.execution_views import _status_document

    job = _job(
        stage="table_extraction",
        stages={"table_extraction": {"status": "done", "seconds": 12.5}},
    )
    doc = _status_document(job)

    assert TABLE_EXTRACTOR_NAME in doc["extractors"]
    assert V1_EXTRACTOR_NAME not in doc["extractors"]
    # R7: recorded AND visible. StageReportView persists any stage name the
    # executor sends, but _status_document filters through the extractor's own
    # list -- with the KV list this array would come back empty.
    assert doc["extractors"][TABLE_EXTRACTOR_NAME]["stages"] == [
        {"name": "table_extraction", "status": "done", "seconds": 12.5}
    ]


def test_a_kv_job_still_reports_its_kv_stages():
    from agent_kv.execution_views import _status_document

    job = _job(
        extractor=V1_EXTRACTOR_NAME,
        stage="extraction",
        stages={"document_processing": {"status": "done"}, "extraction": {"status": "running"}},
    )
    doc = _status_document(job)

    names = [s["name"] for s in doc["extractors"][V1_EXTRACTOR_NAME]["stages"]]
    assert names == ["document_processing", "extraction"]


def test_the_result_payload_keys_by_the_extractor_that_ran():
    from agent_kv.execution_views_result import result_payload

    job = _job(
        status=JobStatus.COMPLETED,
        result_ref="ref.json",
        usage_summary={"pages": 3},
    )
    with mock.patch(
        "agent_kv.execution_views_result.read_result",
        return_value={"tables": [{"unit": "A1"}]},
    ):
        payload = result_payload(job)

    assert payload["success"] is True
    assert payload["status"] == "completed"
    assert payload["extractors"][TABLE_EXTRACTOR_NAME] == {"tables": [{"unit": "A1"}]}
    assert payload["usage_summary"]["by_extractor"][TABLE_EXTRACTOR_NAME] == {"pages": 3}
    assert V1_EXTRACTOR_NAME not in payload["extractors"]


def test_the_extractor_column_defaults_to_kv():
    """The migration's default is the historical truth, not a guess: before
    this column existed the API accepted exactly one extractor, always `kv`.
    """
    assert AgentKVJob().extractor == V1_EXTRACTOR_NAME
