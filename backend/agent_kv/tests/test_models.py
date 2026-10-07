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
