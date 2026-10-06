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
from django.db.models.functions import Coalesce  # noqa: E402
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
    """Wire the sweep's two phase queries.

    Phase 2 is `filter(status__in=...).filter(Q(...) | Q(...))` -- two levels,
    because the age test is an OR: `dispatched_at < cutoff` OR
    `dispatched_at IS NULL AND created_at < cutoff`. A `__lt` filter alone can
    never match a NULL (SQL `NULL < x` is not true), so without that second arm
    a DISPATCHED/RUNNING row with a NULL `dispatched_at` hangs forever.
    """
    phase1_qs = mock.MagicMock()
    phase1_qs.order_by.return_value.__getitem__.return_value = list(never_dispatched)
    phase2_status_qs = mock.MagicMock()
    phase2_qs = phase2_status_qs.filter.return_value
    phase2_qs.order_by.return_value.__getitem__.return_value = list(stuck)
    m_objects.filter.side_effect = [phase1_qs, phase2_status_qs]
    return phase1_qs, phase2_qs, phase2_status_qs


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
    phase1_qs, phase2_qs, phase2_status_qs = _wire_sweep_phases(m_objects)

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
    phase1_qs, phase2_qs, phase2_status_qs = _wire_sweep_phases(m_objects)

    with mock.patch.object(timezone, "now", return_value=frozen_now):
        resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0, "timed_out": 0}
    filter_kwargs = m_objects.filter.call_args_list[1].kwargs
    assert set(filter_kwargs["status__in"]) == {JobStatus.DISPATCHED, JobStatus.RUNNING}
    cutoff = frozen_now - timedelta(seconds=settings.AGENT_KV_STUCK_JOB_GRACE_SECONDS)
    # The age test is an OR, and the second arm is load-bearing: a `__lt`
    # filter alone can never match a NULL `dispatched_at`, so such a row would
    # be invisible to this phase AND to phase 1 (which requires PENDING), and
    # would hang non-terminal forever. A row with no dispatch time falls back
    # to `created_at` -- the only timestamp it has.
    (age_q,), age_kwargs = phase2_status_qs.filter.call_args
    assert age_kwargs == {}
    assert age_q == (
        Q(dispatched_at__lt=cutoff) | Q(dispatched_at__isnull=True, created_at__lt=cutoff)
    )
    # Coalesce, NOT a bare "dispatched_at". This assertion used to pin the
    # bare column, which is the bug: Postgres sorts ascending NULLS LAST, so
    # with a full batch of non-NULL stuck rows ahead of them, the
    # `dispatched_at IS NULL` rows the second Q arm exists to recover were
    # never selected. The backstop could not fire in exactly the situation it
    # exists for -- a backlog. (2.14 in the branch review.)
    phase2_qs.order_by.assert_called_once_with(Coalesce("dispatched_at", "created_at"))
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


class _Lane:
    """One of run_ttl_cleanup's two candidate queries, recording how it was used.

    A real object rather than a ``Mock``: the lane is sorted and then SLICED,
    and a Mock whose ``__getitem__`` is wrapped to record the slice ends up
    calling itself (the wrapper re-enters the same mock), which is how the
    first version of this helper recursed instead of asserting.
    """

    def __init__(self, rows):
        self.rows = list(rows)
        self.order_by_args = None
        self.slice = None

    def order_by(self, *args):
        self.order_by_args = args
        return self

    def __getitem__(self, sl):
        self.slice = sl
        return self.rows[sl]


class _Lanes:
    """Stand-in for the narrowed expired queryset, dispatching to either lane.

    run_ttl_cleanup narrows the expired set once and queries it TWICE --
    ``cleanup_failed_at__isnull=False`` (retries, a reserved slice) and
    ``...=True`` (new expirations, the remainder). A plain ``Mock`` hands back
    the same child for both calls regardless of arguments, so the two lanes
    would yield identical rows and every job would be processed twice.
    """

    def __init__(self, retries, fresh):
        self.retry = _Lane(retries)
        self.fresh = _Lane(fresh)
        self.filter_kwargs: list[dict] = []

    def filter(self, *_args, **kwargs):
        self.filter_kwargs.append(kwargs)
        is_null = kwargs.get("cleanup_failed_at__isnull")
        return self.retry if is_null is False else self.fresh


def _ttl_lanes(m_objects, *, retries=(), fresh=()):
    """Wire a mocked ``AgentKVJob.objects`` to both TTL-cleanup lanes.

    Three chained filters now: `expires_at < now`, then TERMINAL-only (2.15 --
    a running job must not have its input deleted out from under it), then the
    non-blank-ref Q.
    """
    lanes = _Lanes(retries, fresh)
    m_objects.filter.return_value.filter.return_value.filter.return_value = lanes
    return lanes


# (6) the candidate query is exactly expires_at < now AND (non-blank
# input_ref OR non-blank result_ref), capped at 500 across both lanes.
# This is what proves BOTH "non-expired untouched" (the expires_at__lt
# half) and "blank-ref rows excluded / second run is a no-op" (the Q half:
# a row TTLCleanupView just blanked no longer satisfies `__gt=""`).
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_queries_expired_jobs_with_a_nonblank_ref(m_objects, m_delete):
    frozen_now = timezone.now()
    lanes = _ttl_lanes(m_objects)

    with mock.patch.object(timezone, "now", return_value=frozen_now):
        resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"cleaned": 0, "retained": 0}
    assert m_objects.filter.call_args_list[0].kwargs == {"expires_at__lt": frozen_now}
    # TERMINAL-only: a job still RUNNING past its TTL must keep its staged
    # input. The retention policy covers finished work, not running work.
    status_filter = m_objects.filter.return_value.filter.call_args
    assert set(status_filter.kwargs["status__in"]) == set(AgentKVJob.TERMINAL)
    (q_arg,), q_kwargs = (
        m_objects.filter.return_value.filter.return_value.filter.call_args
    )
    assert q_kwargs == {}
    assert q_arg == (Q(input_ref__gt="") | Q(result_ref__gt=""))
    # Two lanes off that one narrowed set: retries first, then new expirations.
    assert lanes.filter_kwargs == [
        {"cleanup_failed_at__isnull": False},
        {"cleanup_failed_at__isnull": True},
    ]
    assert not m_delete.called


# (6b) each lane sorts by a SINGLE named column ascending -- never
# `cleanup_failed_at NULLS FIRST`. A btree index is NULLS LAST ascending, so
# that ordering could not use the (cleanup_failed_at, expires_at) index at all
# and Postgres had to sort every matching expired row before applying the
# limit, work that grows with the backlog. Splitting the query removed it.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_lanes_sort_by_a_plain_ascending_column(m_objects, m_delete):
    lanes = _ttl_lanes(m_objects)

    iv.TTLCleanupView.as_view()(_post("/x"))

    assert lanes.retry.order_by_args == ("cleanup_failed_at",)
    assert lanes.fresh.order_by_args == ("expires_at",)


# (6c) with nothing to retry, the fresh lane still gets the WHOLE batch -- the
# reserve is a cap on the retry lane, not a permanent tax on the normal case.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_fresh_lane_gets_the_whole_batch_when_nothing_is_retrying(
    m_objects, m_delete
):
    lanes = _ttl_lanes(m_objects)

    iv.TTLCleanupView.as_view()(_post("/x"))

    assert lanes.retry.slice == slice(None, 100, None)
    assert lanes.fresh.slice == slice(None, 500, None)


# (6d) THE fix for the second starvation direction. With the retry lane full,
# the fresh lane shrinks by exactly that many, so the two together never exceed
# the batch cap -- and crucially the retry lane is served FIRST, so a steady
# stream of new expirations can no longer push retries out of every batch and
# leave their files in storage indefinitely. Both orderings tried before this
# starved one side: oldest-expiry-first starved fresh work, NULLS FIRST starved
# retries.
@mock.patch.object(maintenance, "delete_job_files", return_value=["input_ref"])
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_reserves_capacity_for_retries_under_a_flood_of_new_expiries(
    m_objects, m_delete
):
    retries = [
        AgentKVJob(id=uuid.uuid4(), input_ref=f"r{i}", cleanup_failed_at=timezone.now())
        for i in range(100)
    ]
    fresh = [AgentKVJob(id=uuid.uuid4(), input_ref=f"f{i}") for i in range(500)]
    lanes = _ttl_lanes(m_objects, retries=retries, fresh=fresh)

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert lanes.retry.slice == slice(None, 100, None)
    assert lanes.fresh.slice == slice(None, 400, None)
    # Every retry was attempted even though 500 fresh rows were queued behind
    # them, and the batch cap still held: 100 + 400 == 500.
    assert m_delete.call_count == 500
    assert resp.data == {"cleaned": 0, "retained": 500}


# (7) files are deleted BEFORE the refs are blanked -- order matters: a
# delete failure must not blank a ref pointing at a file that's still there.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_deletes_files_before_blanking_refs(m_objects, m_delete):
    job_id = uuid.uuid4()
    job = AgentKVJob(
        id=job_id, input_ref="org/o/j/input.pdf", result_ref="org/o/j/result.json"
    )
    m_delete.return_value = ["input_ref", "result_ref"]
    m_qs = m_objects.filter.return_value
    _ttl_lanes(m_objects, fresh=[job])

    manager = mock.Mock()
    manager.attach_mock(m_delete, "delete_job_files")
    manager.attach_mock(m_qs.update, "update")

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"cleaned": 1, "retained": 0}
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
    m_delete.return_value = ["input_ref", "result_ref"]
    m_qs = m_objects.filter.return_value
    _ttl_lanes(m_objects, fresh=[job])

    iv.TTLCleanupView.as_view()(_post("/x"))

    assert m_objects.filter.call_args_list[-1].kwargs == {"id": job_id}
    m_qs.update.assert_called_once_with(
        input_ref="", result_ref="", cleanup_failed_at=None
    )
    assert not m_qs.delete.called


# (9) `cleaned` counts jobs actually processed this call, across multiple
# candidates.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_returns_count_of_jobs_cleaned(m_objects, m_delete):
    job1 = AgentKVJob(id=uuid.uuid4(), input_ref="a", result_ref="")
    job2 = AgentKVJob(id=uuid.uuid4(), input_ref="", result_ref="b")
    m_delete.return_value = ["input_ref", "result_ref"]
    m_qs = m_objects.filter.return_value
    _ttl_lanes(
        m_objects,
        fresh=[
            job1,
            job2,
        ],
    )

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.data == {"cleaned": 2, "retained": 0}
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
    _ttl_lanes(m_objects, fresh=[])

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"cleaned": 0, "retained": 0}
    assert not m_delete.called
    assert not m_qs.update.called


# (10b) THE case test (7)'s comment claims ("a delete failure must not blank a
# ref pointing at a file that's still there") but which nothing actually
# asserted until the Greptile review: test (7) only pinned the ORDER of the two
# calls, and ordering is irrelevant when the update blanks both refs regardless
# of what the delete returned. Before the fix this test fails -- `update` is
# called with both refs blanked and the still-present result file loses its only
# handle, since the candidate query below matches only rows with a non-blank
# ref.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_keeps_the_ref_whose_file_delete_failed(m_objects, m_delete):
    job_id = uuid.uuid4()
    job = AgentKVJob(
        id=job_id, input_ref="org/o/j/input.pdf", result_ref="org/o/j/result.json"
    )
    # Input gone, result delete raised inside delete_job_files.
    m_delete.return_value = ["input_ref"]
    m_qs = m_objects.filter.return_value
    _ttl_lanes(m_objects, fresh=[job])

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    # Only the confirmed-gone ref is blanked; result_ref is NOT in the update,
    # so the row still matches `result_ref__gt=""` and the next pass retries.
    (), kwargs = m_qs.update.call_args
    assert kwargs["input_ref"] == ""
    assert "result_ref" not in kwargs
    # Stamped so the nulls-first ordering pushes this row behind all never-failed
    # work on the next tick -- retried, but unable to block the backlog.
    assert kwargs["cleanup_failed_at"] is not None
    # Not counted as cleaned -- it is unfinished, and `retained` is what makes a
    # permanently-failing backlog visible instead of silently draining to zero.
    assert resp.data == {"cleaned": 0, "retained": 1}


# (10c) nothing confirmed gone -> no ref is blanked, but the failure is still
# recorded. Skipping the write entirely would leave cleanup_failed_at NULL, and
# a NULL sorts FIRST under the candidate ordering -- so the row would hold the
# head of every batch indefinitely, which is the starvation this ordering
# exists to prevent.
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_blanks_no_ref_but_still_stamps_the_failure(m_objects, m_delete):
    job = AgentKVJob(
        id=uuid.uuid4(), input_ref="org/o/j/input.pdf", result_ref="org/o/j/r.json"
    )
    m_delete.return_value = []
    m_qs = m_objects.filter.return_value
    _ttl_lanes(m_objects, fresh=[job])

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    # No ref is blanked -- but the failure IS stamped, or the row would sort
    # nulls-first forever and keep its place at the head of every batch.
    (), kwargs = m_qs.update.call_args
    assert kwargs == {"cleanup_failed_at": mock.ANY}
    assert kwargs["cleanup_failed_at"] is not None
    assert resp.data == {"cleaned": 0, "retained": 1}


# (10d) a row that failed before and succeeds now must have its stale failure
# marker cleared. It drops out of the candidate filter anyway (both refs blank),
# so this matters for the audit trail and for anything reading
# cleanup_failed_at as "currently failing" rather than "failed once".
@mock.patch.object(maintenance, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_clears_a_stale_failure_marker_on_success(m_objects, m_delete):
    job = AgentKVJob(
        id=uuid.uuid4(),
        input_ref="org/o/j/input.pdf",
        result_ref="org/o/j/result.json",
        cleanup_failed_at=timezone.now(),
    )
    m_delete.return_value = ["input_ref", "result_ref"]
    m_qs = m_objects.filter.return_value
    _ttl_lanes(m_objects, fresh=[job])

    resp = iv.TTLCleanupView.as_view()(_post("/x"))

    m_qs.update.assert_called_once_with(
        input_ref="", result_ref="", cleanup_failed_at=None
    )
    assert resp.data == {"cleaned": 1, "retained": 0}


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
