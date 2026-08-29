"""Agent-KV never-dispatched sweep and TTL cleanup internal endpoints
(spec §5.4, task-14-brief.md).

Same mock-based style as test_internal_views.py: no real DB, every
``AgentKVJob.objects`` (and, for TTLCleanupView, ``delete_job_files``) call
is mocked and its arguments/ordering are asserted directly. That is also
the mechanism for the two predicate-shaped guarantees in the brief that a
mock can't literally execute against a database:

* "non-expired jobs untouched" -- proven by asserting the exact
  ``expires_at__lt`` filter kwarg the candidate query is built with.
* "blank-ref rows excluded / a second run over the same set is a no-op" --
  proven by asserting the exact ``Q(input_ref__gt="") | Q(result_ref__gt="")``
  filter the candidate query is built with: a row TTLCleanupView just
  blanked no longer satisfies that predicate, so it drops out of the next
  call's candidate set.

These tests exercise the two-phase sweep and TTL-cleanup logic through the
(now-thin) ``SweepView``/``TTLCleanupView`` -- the logic itself lives in
``agent_kv.maintenance`` (moved there so the ``agent_kv_sweep``/
``agent_kv_ttl_cleanup`` management commands can share it), which is why
``delete_job_files`` is patched on the ``maintenance`` module below rather
than on ``internal_views``.
"""

import os
import uuid
from datetime import timedelta
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.conf import settings  # noqa: E402
from django.db.models import Q  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from agent_kv import internal_views as iv  # noqa: E402
from agent_kv import maintenance  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def _post(path, body=None):
    return APIRequestFactory().post(path, body or {}, format="json")


# ---------------------------------------------------------------------------
# SweepView
# ---------------------------------------------------------------------------
#
# SweepView runs two independent phases per call -- never-dispatched PENDING
# jobs, then stuck DISPATCHED/RUNNING jobs -- each its own
# filter().order_by()[:500] chain against the same (mocked) AgentKVJob.objects
# manager. ``_wire_sweep_phases`` gives each phase call its own Mock object
# (via `side_effect`, keyed on call ORDER: phase 1 first, then phase 2) so a
# test can assert on -- and control the candidates of -- one phase without the
# other phase's identical-shaped chain aliasing it.


def _wire_sweep_phases(m_objects, never_dispatched=(), stuck=()):
    phase1_qs = mock.MagicMock()
    phase1_qs.order_by.return_value.__getitem__.return_value = list(never_dispatched)
    phase2_qs = mock.MagicMock()
    phase2_qs.order_by.return_value.__getitem__.return_value = list(stuck)
    m_objects.filter.side_effect = [phase1_qs, phase2_qs]
    return phase1_qs, phase2_qs


# (1) the never-dispatched-phase candidate query is exactly PENDING + older
# than the grace + dispatched_at IS NULL -- assert the filter kwargs directly
# (this IS the proof that "only PENDING+old+undispatched" are swept; nothing
# else does a real DB round trip in this suite) -- and, per the task-14-review
# ruling, oldest-created-first and capped at 500: an unbounded queryset would
# load a whole infra-incident backlog into memory and hold the request open
# through it, exactly when the sweep matters most.
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_queries_pending_older_than_grace_and_undispatched(
    m_objects, m_mark_terminal
):
    frozen_now = timezone.now()
    phase1_qs, phase2_qs = _wire_sweep_phases(m_objects)

    with mock.patch.object(timezone, "now", return_value=frozen_now):
        resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0, "timed_out": 0}
    filter_kwargs = m_objects.filter.call_args_list[0].kwargs
    assert filter_kwargs["status"] == JobStatus.PENDING
    assert filter_kwargs["dispatched_at__isnull"] is True
    assert filter_kwargs["created_at__lt"] == frozen_now - timedelta(
        seconds=settings.AGENT_KV_SWEEP_GRACE_SECONDS
    )
    phase1_qs.order_by.assert_called_once_with("created_at")
    phase1_qs.order_by.return_value.__getitem__.assert_called_once_with(
        slice(None, 500, None)
    )
    assert not m_mark_terminal.called


# (2) each never-dispatched candidate is terminalized via
# mark_terminal(FAILED, "Job was never dispatched") -- the guarded write, not
# a raw .update().
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_terminalizes_each_candidate_as_failed_never_dispatched(
    m_objects, m_mark_terminal, m_release
):
    job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    _wire_sweep_phases(m_objects, never_dispatched=[job])
    m_mark_terminal.return_value = True

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    m_mark_terminal.assert_called_once_with(
        job.id, "org1", JobStatus.FAILED, error="Job was never dispatched"
    )


# (3) a job the guard actually wins gets its concurrency slot released, with
# its own org id and job id.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_releases_the_concurrency_slot_of_each_swept_job(
    m_objects, m_mark_terminal, m_release
):
    job = AgentKVJob(id=uuid.uuid4(), organization_id="org7")
    _wire_sweep_phases(m_objects, never_dispatched=[job])
    m_mark_terminal.return_value = True

    iv.SweepView.as_view()(_post("/x"))

    m_release.assert_called_once_with("org7", str(job.id))


# (4) a candidate that LOSES the mark_terminal guard (raced to terminal by
# a concurrent finalize/cancel/duplicate sweep between the candidate read
# and the guarded write) is not counted as swept and its slot is not
# released here -- whichever path won the race already released it.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_count_reflects_guard_outcomes_not_candidate_count(
    m_objects, m_mark_terminal, m_release
):
    won_job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    lost_job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    _wire_sweep_phases(m_objects, never_dispatched=[won_job, lost_job])
    m_mark_terminal.side_effect = [True, False]

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 1, "timed_out": 0}
    m_release.assert_called_once_with("org1", str(won_job.id))


# (5) no candidates -> {"swept": 0, "timed_out": 0}, and no terminalize/
# release side effects.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_with_no_candidates_is_a_pure_noop(m_objects, m_mark_terminal, m_release):
    _wire_sweep_phases(m_objects)

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0, "timed_out": 0}
    assert not m_mark_terminal.called
    assert not m_release.called


# ---------------------------------------------------------------------------
# SweepView -- stuck-job (phase 2) terminalizer (Fix 8)
# ---------------------------------------------------------------------------


# (5a) the stuck-job-phase candidate query is exactly
# DISPATCHED/RUNNING + dispatched_at older than the stuck grace, ordered
# oldest-dispatched-first and capped at 500 -- same batch-safety rationale as
# phase 1.
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_stuck_sweep_queries_dispatched_and_running_older_than_stuck_grace(
    m_objects, m_mark_terminal
):
    frozen_now = timezone.now()
    phase1_qs, phase2_qs = _wire_sweep_phases(m_objects)

    with mock.patch.object(timezone, "now", return_value=frozen_now):
        resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0, "timed_out": 0}
    filter_kwargs = m_objects.filter.call_args_list[1].kwargs
    assert set(filter_kwargs["status__in"]) == {JobStatus.DISPATCHED, JobStatus.RUNNING}
    assert filter_kwargs["dispatched_at__lt"] == frozen_now - timedelta(
        seconds=settings.AGENT_KV_STUCK_JOB_GRACE_SECONDS
    )
    phase2_qs.order_by.assert_called_once_with("dispatched_at")
    phase2_qs.order_by.return_value.__getitem__.assert_called_once_with(
        slice(None, 500, None)
    )
    assert not m_mark_terminal.called


# (5b) each stuck candidate is terminalized via mark_terminal(FAILED,
# "Job timed out") -- distinct error text from the never-dispatched phase.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_stuck_sweep_terminalizes_each_candidate_as_failed_timed_out(
    m_objects, m_mark_terminal, m_release
):
    job = AgentKVJob(id=uuid.uuid4(), organization_id="org1", status=JobStatus.RUNNING)
    _wire_sweep_phases(m_objects, stuck=[job])
    m_mark_terminal.return_value = True

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0, "timed_out": 1}
    m_mark_terminal.assert_called_once_with(
        job.id, "org1", JobStatus.FAILED, error="Job timed out"
    )


# (5c) a stuck job the guard wins gets its concurrency slot released.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_stuck_sweep_releases_the_concurrency_slot_of_each_timed_out_job(
    m_objects, m_mark_terminal, m_release
):
    job = AgentKVJob(id=uuid.uuid4(), organization_id="org9", status=JobStatus.DISPATCHED)
    _wire_sweep_phases(m_objects, stuck=[job])
    m_mark_terminal.return_value = True

    iv.SweepView.as_view()(_post("/x"))

    m_release.assert_called_once_with("org9", str(job.id))


# (5d) a stuck candidate that LOSES the guard (raced to terminal by a
# concurrent finalize/cancel/duplicate sweep) is not counted as timed_out and
# its slot is not released here.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_stuck_sweep_count_reflects_guard_outcomes_not_candidate_count(
    m_objects, m_mark_terminal, m_release
):
    won_job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    lost_job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    _wire_sweep_phases(m_objects, stuck=[won_job, lost_job])
    m_mark_terminal.side_effect = [True, False]

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0, "timed_out": 1}
    m_release.assert_called_once_with("org1", str(won_job.id))


# (5e) the two phases' counts are independent -- a hit in one phase doesn't
# affect the other's count, and both run on the same call.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_reports_both_phase_counts_independently(
    m_objects, m_mark_terminal, m_release
):
    never_dispatched_job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    stuck_job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    _wire_sweep_phases(
        m_objects, never_dispatched=[never_dispatched_job], stuck=[stuck_job]
    )
    m_mark_terminal.return_value = True

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 1, "timed_out": 1}


# ---------------------------------------------------------------------------
# TTLCleanupView
# ---------------------------------------------------------------------------


# (6) the candidate query is exactly expires_at < now AND (non-blank
# input_ref OR non-blank result_ref), oldest-expired first, capped at 500.
# This is what proves BOTH "non-expired untouched" (the expires_at__lt
# half) and "blank-ref rows excluded / second run is a no-op" (the Q half:
# a row TTLCleanupView just blanked no longer satisfies `__gt=""`).
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_queries_expired_jobs_with_a_nonblank_ref(m_objects, m_delete):
    frozen_now = timezone.now()
    m_expiry_qs = m_objects.filter.return_value
    m_ref_qs = m_expiry_qs.filter.return_value
    m_ordered_qs = m_ref_qs.order_by.return_value
    m_ordered_qs.__getitem__.return_value = []

    with mock.patch.object(timezone, "now", return_value=frozen_now):
        resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"cleaned": 0}
    assert m_objects.filter.call_args_list[0].kwargs == {"expires_at__lt": frozen_now}
    (q_arg,), q_kwargs = m_expiry_qs.filter.call_args
    assert q_kwargs == {}
    assert q_arg == (Q(input_ref__gt="") | Q(result_ref__gt=""))
    m_ref_qs.order_by.assert_called_once_with("expires_at")
    m_ordered_qs.__getitem__.assert_called_once_with(slice(None, 500, None))
    assert not m_delete.called


# (7) files are deleted BEFORE the refs are blanked -- order matters: a
# delete failure must not blank a ref pointing at a file that's still there.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_deletes_files_before_blanking_refs(m_objects, m_delete):
    job_id = uuid.uuid4()
    job = AgentKVJob(
        id=job_id, input_ref="org/o/j/input.pdf", result_ref="org/o/j/result.json"
    )
    m_qs = m_objects.filter.return_value
    m_qs.filter.return_value.order_by.return_value.__getitem__.return_value = [job]

    manager = mock.Mock()
    manager.attach_mock(m_delete, "delete_job_files")
    manager.attach_mock(m_qs.update, "update")

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"cleaned": 1}
    assert [c[0] for c in manager.mock_calls] == ["delete_job_files", "update"]
    m_delete.assert_called_once_with(job)


# (8) both refs are blanked via `.update()` (not `job.save()`), targeting
# exactly this job's row, and the row itself is left in place (no .delete()
# call is ever made on the queryset).
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_blanks_both_refs_for_the_job_row(m_objects, m_delete):
    job_id = uuid.uuid4()
    job = AgentKVJob(id=job_id, input_ref="org/o/j/input.pdf", result_ref="")
    m_qs = m_objects.filter.return_value
    m_qs.filter.return_value.order_by.return_value.__getitem__.return_value = [job]

    iv.TTLCleanupView.as_view()(_post("/x"))

    assert m_objects.filter.call_args_list[-1].kwargs == {"id": job_id}
    m_qs.update.assert_called_once_with(input_ref="", result_ref="")
    assert not m_qs.delete.called


# (9) `cleaned` counts jobs actually processed this call, across multiple
# candidates.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_returns_count_of_jobs_cleaned(m_objects, m_delete):
    job1 = AgentKVJob(id=uuid.uuid4(), input_ref="a", result_ref="")
    job2 = AgentKVJob(id=uuid.uuid4(), input_ref="", result_ref="b")
    m_qs = m_objects.filter.return_value
    m_qs.filter.return_value.order_by.return_value.__getitem__.return_value = [
        job1,
        job2,
    ]

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.data == {"cleaned": 2}
    assert m_delete.call_count == 2
    assert m_qs.update.call_count == 2


# (10) no candidates -> {"cleaned": 0}, nothing deleted or updated. This is
# also the concrete shape of a "second run over the same set" once every
# candidate from the first run has had its refs blanked: the (mocked)
# candidate query simply returns nothing.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_with_no_candidates_is_a_pure_noop(m_objects, m_delete):
    m_qs = m_objects.filter.return_value
    m_qs.filter.return_value.order_by.return_value.__getitem__.return_value = []

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"cleaned": 0}
    assert not m_delete.called
    assert not m_qs.update.called


# ---------------------------------------------------------------------------
# URL wiring
# ---------------------------------------------------------------------------


# (11) regression pin for the frozen paths (spec Interfaces block): the
# PG-scheduler/reaper periodic mechanism calls these exact URLs, so a
# dropped/renamed include in internal_base_urls.py must fail loudly here
# rather than 404 in prod.
def test_frozen_sweep_and_ttl_cleanup_urls_resolve_to_the_right_views():
    from django.urls import resolve

    sweep = resolve("/internal/v1/agent-kv/sweep/")
    assert sweep.func.cls is iv.SweepView

    ttl_cleanup = resolve("/internal/v1/agent-kv/ttl-cleanup/")
    assert ttl_cleanup.func.cls is iv.TTLCleanupView
