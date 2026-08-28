"""Terminal-state write guard: the invariant everything else leans on (spec §5.4)."""
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def test_terminal_set_is_exactly_the_three_states():
    assert AgentKVJob.TERMINAL == frozenset(
        {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    )


@mock.patch.object(AgentKVJob, "objects")
def test_mark_terminal_excludes_terminal_rows_and_reports_success(m_objects):
    m_qs = m_objects.filter.return_value.exclude.return_value
    m_qs.update.return_value = 1
    ok = AgentKVJob.mark_terminal(
        job_id=uuid.uuid4(), organization_id="org1",
        new_status=JobStatus.FAILED, error="boom",
    )
    assert ok is True
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
        job_id=uuid.uuid4(), organization_id="org1",
        new_status=JobStatus.COMPLETED,
    )
    assert ok is False
