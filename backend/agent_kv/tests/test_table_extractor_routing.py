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

from django.test import override_settings  # noqa: E402

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


def test_both_extractors_are_supported_through_the_one_api():
    """One endpoint, one selector, two engines.

    A caller chooses with `extractors[].name`; there is no separate KV endpoint
    and no second parameter. `SUPPORTED_EXTRACTORS` is derived from
    `EXTRACTOR_ROUTES`, so this asserts the selector's accepted values exactly
    -- both present, and nothing else accepted by accident.

    This replaces `test_table_is_the_only_supported_extractor`, which asserted
    `kv` was absent. That was correct only while the engine shipped on its own
    branch and nothing drained `celery_executor_agentic_kv`; both fleets drain
    it now (see `test_queue_wiring_is_derived.py`, which derives that check
    from this very table rather than restating it).
    """
    assert set(SUPPORTED_EXTRACTORS) == {V1_EXTRACTOR_NAME, TABLE_EXTRACTOR_NAME}


def test_the_kv_route_targets_the_shipped_executor():
    """The pair here must match what the plugin registers, or submits are
    accepted with a 202 and dispatched to a queue nothing drains.

    Verified against a running deployment when `kv` was enabled:
    `agentic_kv.constants` gives `EXECUTOR_NAME == "agentic_kv"` and
    `OPERATION_KV_EXTRACT == "kv_extract"`, and `AgenticKVExecutor` rejects any
    other operation. The queue name is DERIVED from the executor name, so a
    typo here is not a 500 -- it is silence.
    """
    executor, operation = EXTRACTOR_ROUTES[V1_EXTRACTOR_NAME]
    assert executor == "agentic_kv"
    assert operation == "kv_extract"


def test_every_supported_extractor_has_a_route_stage_list_and_options_serializer():
    """A supported extractor with no route dispatches nowhere; with no stage
    list its progress is recorded and then filtered out of the status
    document; with no options serializer, a submit for it raises an
    uncaught KeyError at `_OPTIONS_SERIALIZERS[data["name"]]` instead of a
    validation error -- `validate_name` already passed it, since
    `SUPPORTED_EXTRACTORS` is derived from `EXTRACTOR_ROUTES`.
    """
    from agent_kv.execution_serializers import _ADAPTERS_SERIALIZERS

    for name in SUPPORTED_EXTRACTORS:
        assert name in EXTRACTOR_ROUTES, name
        assert name in STAGE_NAMES_BY_EXTRACTOR, name
        assert name in _OPTIONS_SERIALIZERS, name
        # Both shipped engines run on caller-supplied adapters, so an absent
        # entry here is not "this extractor takes none" any more -- it is a
        # submit refused with "takes no adapters" for an engine that requires
        # them. If an extractor is ever added that genuinely needs none, this
        # assertion is the one to relax, deliberately and with a reason.
        assert name in _ADAPTERS_SERIALIZERS, name


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


@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=True)
def test_a_kv_entry_is_accepted_with_its_own_keys_and_options():
    """The positive case the old `test_a_kv_entry_is_refused_by_name` denied.

    `kv`'s `keys` is a compiled schema rather than a fixed field set (it is
    absent from `_KEYS_SERIALIZERS` on purpose), and `qa` is one of its own
    options -- an option the table extractor rejects. So this one payload
    exercises the whole point of extractor-scoping: the same request shape
    carries a different schema language and a different knob set depending on
    one parameter.
    """
    s = ExtractorSerializer(
        data={
            "name": "kv",
            "keys": {"total": {"description": "d"}},
            "options": {"qa": False},
            "adapters": {
                "llm": "11111111-1111-1111-1111-111111111111",
                "lite_llm": "22222222-2222-2222-2222-222222222222",
                "x2text": "33333333-3333-3333-3333-333333333333",
            },
        }
    )
    assert s.is_valid(), json.dumps(s.errors)
    assert s.validated_data["name"] == "kv"


def test_an_unknown_extractor_is_still_refused_by_name():
    """Enabling `kv` must not turn the selector into a free-text field.

    The refusal has to name the offending value, so a typo reads as a typo
    rather than as a schema complaint about `keys`.
    """
    s = ExtractorSerializer(data={"name": "kvv", "keys": {"total": {"description": "d"}}})
    assert not s.is_valid()
    assert "unknown extractor" in json.dumps(s.errors)
    assert "kvv" in json.dumps(s.errors)


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


def test_kv_is_wired_in_every_table_a_routable_extractor_needs():
    """Four tables, not one: route, stage list, options and adapters.

    `test_every_supported_extractor_has_a_route_stage_list_and_options_serializer`
    derives the first three from `SUPPORTED_EXTRACTORS`; this names `kv`'s
    entries explicitly so a reader can see what enabling an extractor consists
    of without running the derivation in their head. Miss the stage list and
    the job's progress is recorded and then filtered out of every status
    response; miss the options serializer and a submit raises KeyError rather
    than a validation error; miss the adapters entry and a `kv` submit that
    names adapters is refused with "takes no adapters" while the engine
    demands them.

    This was `test_the_kv_route_constants_survive_for_re_enablement`, which
    asserted the same constants for the opposite reason -- that they outlived
    `kv` being unroutable so the engine's branch could re-enable it by
    restoring one dict entry. That is what happened; the assertions are worth
    keeping, the premise is spent.
    """
    from agent_kv.constants import (
        EXECUTOR_NAME,
        OPERATION_KV_EXTRACT,
        STAGE_NAMES_BY_EXTRACTOR,
    )
    from agent_kv.execution_serializers import (
        _ADAPTERS_SERIALIZERS,
        _OPTIONS_SERIALIZERS,
    )

    assert EXECUTOR_NAME == "agentic_kv"
    assert OPERATION_KV_EXTRACT == "kv_extract"
    assert V1_EXTRACTOR_NAME in EXTRACTOR_ROUTES
    assert V1_EXTRACTOR_NAME in STAGE_NAMES_BY_EXTRACTOR
    assert V1_EXTRACTOR_NAME in _OPTIONS_SERIALIZERS
    assert V1_EXTRACTOR_NAME in _ADAPTERS_SERIALIZERS


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


def test_the_extractor_column_has_no_default():
    """Was `test_the_extractor_column_defaults_to_kv`, asserting `== "kv"`.

    It pinned the defect as the contract. The default WAS the historical truth
    when migration 0002 added the column -- the API accepted exactly one
    extractor and it was always `kv` -- and it became a mis-filing trap the
    moment `table` existed: `kv` is a valid key in `STAGE_NAMES_BY_EXTRACTOR`,
    so a table job filed under it gets the KV stage list and
    `table_extraction` is silently dropped from every status response, with
    nothing logged because nothing looks wrong to the filter.

    `""` matches no route, so an omission now fails the dispatch visibly. The
    row-level truth 0002 back-filled is untouched: existing `kv` rows keep
    saying `kv`, which is what `test_a_job_whose_extractor_has_no_stage_list_
    reports_no_stages` below depends on.
    """
    assert AgentKVJob().extractor == ""
    assert V1_EXTRACTOR_NAME in {
        value for value, _ in AgentKVJob._meta.get_field("extractor").choices
    }, "a pre-carve-out row must still be a legal value to READ back"


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
        "the public route set changed. If `/validate` was added: that is a real "
        "decision, not a typo -- it is a new public, rate-limited, "
        "key-authenticated surface, and it was left unrouted on purpose when "
        "`kv` became routable (see ValidateView's docstring). Update this set "
        "and this message together, or revert the route."
    )


def test_validate_view_documents_that_it_is_unrouted():
    from agent_kv.execution_views import ValidateView

    doc = ValidateView.__doc__ or ""
    assert "NOT ROUTED" in doc, (
        "ValidateView is a complete, decorated, live-looking endpoint that "
        "nothing reaches. Say so on the class, not only in execution_urls.py"
    )


# ---------------------------------------------------------------------------
# Routed is not the same as enabled
# ---------------------------------------------------------------------------
@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=False)
def test_kv_is_refused_where_the_deployment_has_not_enabled_it():
    """The guard that makes merge order safe.

    `EXTRACTOR_ROUTES` says where `kv` work GOES. Nothing in this repo can say
    whether a fleet drains `celery_executor_agentic_kv` -- that queue list
    ships in the chart, and `SubmitView`'s `get_plugin("agent_kv")` probe is
    per-deployment, so it is already truthy wherever `table` shipped.

    Without this gate, merging this repo before the chart accepts a `kv` submit
    with a 202, stages the file, takes a concurrency slot shared with `table`,
    and leaves the row in DISPATCHED until the sweep force-fails it -- with no
    error at the producer.
    """
    from agent_kv.execution_serializers import ExtractorSerializer

    s = ExtractorSerializer(
        data={"name": "kv", "keys": {"total": {"description": "Grand total"}}}
    )
    assert not s.is_valid()
    msg = str(s.errors)
    assert "not enabled on this deployment" in msg, msg
    # Refused as DISABLED, not as unknown: the deployment has to change, not
    # the request, and an integrator told "unknown" goes looking for a typo.
    assert "unknown extractor" not in msg, msg


@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=False)
def test_table_is_unaffected_when_kv_is_disabled():
    """The gate is per-extractor. Disabling `kv` must not touch the extractor
    that has shipped and does drain its queue.
    """
    from agent_kv.execution_serializers import ExtractorSerializer

    s = ExtractorSerializer(
        data={"name": "table", "keys": {"target_table": "Line items"}}
    )
    assert s.is_valid(), str(s.errors)


def test_enabled_extractors_tracks_the_flag_in_both_directions():
    """Pins the derivation itself, not just one branch of it."""
    from django.test import override_settings as _os

    from agent_kv.execution_serializers import (
        SUPPORTED_EXTRACTORS,
        enabled_extractors,
    )

    with _os(AGENT_KV_KV_EXTRACTOR_ENABLED=True):
        assert set(enabled_extractors()) == set(SUPPORTED_EXTRACTORS)
        assert V1_EXTRACTOR_NAME in enabled_extractors()
    with _os(AGENT_KV_KV_EXTRACTOR_ENABLED=False):
        assert V1_EXTRACTOR_NAME not in enabled_extractors()
        # Routed set is unchanged -- only acceptance moves.
        assert V1_EXTRACTOR_NAME in SUPPORTED_EXTRACTORS
        assert TABLE_EXTRACTOR_NAME in enabled_extractors()
