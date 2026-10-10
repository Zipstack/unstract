"""Terminal-state write guard: the invariant everything else leans on (spec §5.4)."""

import os
import uuid
from unittest import mock

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def test_terminal_set_is_exactly_the_three_states():
    assert AgentKVJob.TERMINAL == frozenset(
        {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    )


@mock.patch.object(AgentKVJob, "objects")
def test_mark_terminal_excludes_terminal_rows_and_reports_success(m_objects):
    m_qs = m_objects.filter.return_value.exclude.return_value
    m_qs.update.return_value = 1
    job_id = uuid.uuid4()
    ok = AgentKVJob.mark_terminal(
        job_id=job_id,
        organization_id="org1",
        new_status=JobStatus.FAILED,
        error="boom",
    )
    assert ok is True
    filter_kwargs = m_objects.filter.call_args.kwargs
    assert filter_kwargs["id"] == job_id
    assert filter_kwargs["organization_id"] == "org1"
    _, exclude_kwargs = m_objects.filter.return_value.exclude.call_args
    assert set(exclude_kwargs["status__in"]) == set(AgentKVJob.TERMINAL)
    update_kwargs = m_qs.update.call_args.kwargs
    assert update_kwargs["status"] == JobStatus.FAILED
    assert update_kwargs["error"] == "boom"
    assert "completed_at" in update_kwargs


@mock.patch.object(AgentKVJob, "objects")
def test_mark_terminal_on_already_terminal_row_is_noop_false(m_objects):
    m_objects.filter.return_value.exclude.return_value.update.return_value = 0
    ok = AgentKVJob.mark_terminal(
        job_id=uuid.uuid4(),
        organization_id="org1",
        new_status=JobStatus.COMPLETED,
    )
    assert ok is False


# --------------------------------------------------------------------------
# 2.16: the guarded UPDATE excludes terminal ROWS, not non-terminal ARGUMENTS.
# --------------------------------------------------------------------------


@mock.patch.object(AgentKVJob, "objects")
@pytest.mark.parametrize(
    "bad_status", [JobStatus.PENDING, JobStatus.DISPATCHED, JobStatus.RUNNING]
)
def test_mark_terminal_refuses_a_non_terminal_status(m_objects, bad_status):
    """`mark_terminal(..., RUNNING)` used to stamp `completed_at=now()`.

    That leaves a row that reads as finished to everything keying off
    `completed_at` (the TTL filter, the sweep's cancelled-job phase) while
    still being invisible to the terminal guard -- so nothing can ever
    terminalize it again. No caller does this today; the method is named for
    the invariant, so it enforces it.
    """
    with pytest.raises(ValueError, match="non-terminal status"):
        AgentKVJob.mark_terminal(
            job_id=uuid.uuid4(),
            organization_id="org1",
            new_status=bad_status,
        )
    assert not m_objects.filter.called, "no write may be attempted"


@mock.patch.object(AgentKVJob, "objects")
@pytest.mark.parametrize("good_status", sorted(AgentKVJob.TERMINAL))
def test_mark_terminal_accepts_every_terminal_status(m_objects, good_status):
    m_objects.filter.return_value.exclude.return_value.update.return_value = 1
    assert (
        AgentKVJob.mark_terminal(
            job_id=uuid.uuid4(),
            organization_id="org1",
            new_status=good_status,
        )
        is True
    )


# --------------------------------------------------------------------------
# 2.17: `extractor` was the one stringly-typed field without `choices`, and it
# defaulted to the extractor this build cannot run.
# --------------------------------------------------------------------------


def test_extractor_declares_its_choices():
    field = AgentKVJob._meta.get_field("extractor")
    assert {value for value, _ in field.choices} == {"kv", "table"}


def test_extractor_has_no_default():
    """An omitted `extractor=` must be loud, not silently filed as `kv`.

    `kv` IS a valid key in `STAGE_NAMES_BY_EXTRACTOR`, so a table job filed
    under it gets the KV stage list and `table_extraction` is dropped from
    every status response -- the job runs, the caller is billed, the stages
    array comes back empty and nothing logs a warning, because nothing is
    wrong as far as the filter can tell.

    With no default the omission produces `""`, which matches no route: the
    dispatch raises, the job terminalizes FAILED with a visible error, and
    `_status_document` logs the unknown-extractor warning.
    """
    field = AgentKVJob._meta.get_field("extractor")
    assert not field.has_default(), (
        "migration 0002's `default='kv'` was the historical truth then and is "
        "a mis-filing trap now; see the field comment"
    )
    assert AgentKVJob(organization_id="o").extractor == ""


def test_recordable_extractors_are_a_superset_of_routable_ones():
    """The two sets are deliberately different, so neither is derived.

    `choices` says what a ROW may record -- rows written before the carve-out
    legitimately say `kv`. `EXTRACTOR_ROUTES` says what a submit may DISPATCH,
    and `kv` is absent from it on purpose. Deriving either from the other
    would quietly re-enable the extractor or make old rows unreadable.
    """
    from agent_kv.constants import EXTRACTOR_ROUTES

    recordable = {value for value, _ in AgentKVJob._meta.get_field("extractor").choices}
    assert set(EXTRACTOR_ROUTES) < recordable, (
        "every routable extractor must be recordable, and `kv` is recordable "
        "without being routable"
    )
