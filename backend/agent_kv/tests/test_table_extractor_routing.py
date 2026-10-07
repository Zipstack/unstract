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

from agent_kv.constants import (  # noqa: E402
    EXTRACTOR_ROUTES,
    STAGE_NAMES_BY_EXTRACTOR,
    TABLE_EXTRACTOR_NAME,
    V1_EXTRACTOR_NAME,
)
from agent_kv.execution_serializers import (  # noqa: E402
    _OPTIONS_SERIALIZERS,
    SUPPORTED_EXTRACTORS,
    ExtractorSerializer,
)
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def test_table_is_the_only_supported_extractor():
    """`kv` is out of EXTRACTOR_ROUTES because this deployment ships no
    `agentic_kv` plugin, so nothing drains `celery_executor_agentic_kv`.
    SUPPORTED_EXTRACTORS is derived from that table, so the omission is what
    turns a `kv` submit into a 400 rather than a 202 for a job that never runs.
    """
    assert set(SUPPORTED_EXTRACTORS) == {TABLE_EXTRACTOR_NAME}
    assert V1_EXTRACTOR_NAME not in EXTRACTOR_ROUTES


def test_every_supported_extractor_has_a_route_stage_list_and_options_serializer():
    """A supported extractor with no route dispatches nowhere; with no stage
    list its progress is recorded and then filtered out of the status
    document; with no options serializer, a submit for it raises an
    uncaught KeyError at `_OPTIONS_SERIALIZERS[data["name"]]` instead of a
    validation error -- `validate_name` already passed it, since
    `SUPPORTED_EXTRACTORS` is derived from `EXTRACTOR_ROUTES`.
    """
    for name in SUPPORTED_EXTRACTORS:
        assert name in EXTRACTOR_ROUTES, name
        assert name in STAGE_NAMES_BY_EXTRACTOR, name
        assert name in _OPTIONS_SERIALIZERS, name


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


def test_a_kv_entry_is_refused_by_name():
    """Options scoping is moot for `kv` here: `validate_name` refuses the entry
    before any options validator runs. What matters is that the refusal names
    the extractor, so a caller sending a KV payload to this deployment learns
    why rather than seeing a schema complaint.
    """
    s = ExtractorSerializer(
        data={
            "name": "kv",
            "keys": {"total": {"description": "d"}},
            "options": {"qa": False},
        }
    )
    assert not s.is_valid()
    assert "unknown extractor" in json.dumps(s.errors)
    assert "kv" in json.dumps(s.errors)


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


def test_the_kv_route_constants_survive_for_re_enablement():
    """`kv` is unroutable, not deleted. The executor/operation pair, the stage
    list and the options serializer all stay so the branch carrying the engine
    re-enables the extractor by restoring one dict entry -- not by merging
    content back into the files it rewrites most.
    """
    from agent_kv.constants import (
        EXECUTOR_NAME,
        OPERATION_KV_EXTRACT,
        STAGE_NAMES_BY_EXTRACTOR,
    )
    from agent_kv.execution_serializers import _OPTIONS_SERIALIZERS

    assert EXECUTOR_NAME == "agentic_kv"
    assert OPERATION_KV_EXTRACT == "kv_extract"
    assert V1_EXTRACTOR_NAME in STAGE_NAMES_BY_EXTRACTOR
    assert V1_EXTRACTOR_NAME in _OPTIONS_SERIALIZERS


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
        stages={
            "document_processing": {"status": "done"},
            "extraction": {"status": "running"},
        },
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


def test_a_job_whose_extractor_has_no_stage_list_reports_no_stages(caplog):
    """A retired extractor name with surviving rows must not 500 `GET status`.

    `_status_document` used to subscript `STAGE_NAMES_BY_EXTRACTOR`, so such a
    row raised `KeyError` on status while `GET result` kept working -- the
    result payload keys by `job.extractor` without consulting that table. An
    empty stage array is the honest answer for an extractor this build no
    longer knows how to describe.
    """
    from agent_kv.execution_views import _status_document

    job = _job(
        extractor="retired_extractor",
        stage="something",
        stages={"something": {"status": "done"}},
    )

    with caplog.at_level("WARNING", logger="agent_kv.execution_views"):
        doc = _status_document(job)

    assert doc["extractors"]["retired_extractor"]["stages"] == []
    assert doc["status"] == job.status.lower()
    assert "retired_extractor" in caplog.text


# ---------------------------------------------------------------------------
# `ValidateView` is part of the carve-out: the class stays in the tree and the
# route does not. Both halves are asserted here, including that the class says
# so itself -- a reader of `execution_views.py` sees a complete, decorated,
# live-looking endpoint, and the only thing that decided otherwise was a file
# they may never open.
# ---------------------------------------------------------------------------


def test_validate_is_not_a_public_route_on_this_deployment():
    from agent_kv import execution_urls

    names = {p.name for p in execution_urls.urlpatterns}
    assert names == {
        "agent_kv_submit",
        "agent_kv_status",
        "agent_kv_result",
        "agent_kv_cancel",
    }, (
        "the public route set changed; `/validate` compiles a `kv` schema and "
        "`kv` is the one extractor this build refuses, so routing it would "
        "advertise validation for an extractor every submit 400s"
    )


def test_validate_view_documents_that_it_is_unrouted():
    from agent_kv.execution_views import ValidateView

    doc = ValidateView.__doc__ or ""
    assert "NOT ROUTED" in doc, (
        "ValidateView is a complete, decorated, live-looking endpoint that "
        "nothing reaches. Say so on the class, not only in execution_urls.py"
    )
