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
"""

import os
import uuid
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
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def _post(path, body=None):
    return APIRequestFactory().post(path, body or {}, format="json")


# ---------------------------------------------------------------------------
# SweepView
# ---------------------------------------------------------------------------


# (1) the candidate query is exactly PENDING + older than the grace +
# dispatched_at IS NULL -- assert the filter kwargs directly (this IS the
# proof that "only PENDING+old+undispatched" are swept; nothing else does
# a real DB round trip in this suite) -- and, per the task-14-review ruling,
# oldest-created-first and capped at 500: an unbounded queryset would load
# a whole infra-incident backlog into memory and hold the request open
# through it, exactly when the sweep matters most.
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_queries_pending_older_than_grace_and_undispatched(
    m_objects, m_mark_terminal
):
    frozen_now = timezone.now()
    m_qs = m_objects.filter.return_value
    m_ordered_qs = m_qs.order_by.return_value
    m_ordered_qs.__getitem__.return_value = []

    with mock.patch.object(iv.timezone, "now", return_value=frozen_now):
        resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0}
    filter_kwargs = m_objects.filter.call_args.kwargs
    assert filter_kwargs["status"] == JobStatus.PENDING
    assert filter_kwargs["dispatched_at__isnull"] is True
    assert filter_kwargs["created_at__lt"] == frozen_now - iv.timedelta(
        seconds=settings.AGENT_KV_SWEEP_GRACE_SECONDS
    )
    m_qs.order_by.assert_called_once_with("created_at")
    m_ordered_qs.__getitem__.assert_called_once_with(slice(None, 500, None))
    assert not m_mark_terminal.called


def _sweep_candidates(m_objects, jobs):
    """Wire the SweepView candidate chain -- filter().order_by()[:500] --
    to return ``jobs``, mirroring the real queryset chain post-fix.
    """
    m_objects.filter.return_value.order_by.return_value.__getitem__.return_value = jobs


# (2) each candidate is terminalized via mark_terminal(FAILED, "Job was
# never dispatched") -- the guarded write, not a raw .update().
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_terminalizes_each_candidate_as_failed_never_dispatched(
    m_objects, m_mark_terminal, m_release
):
    job = AgentKVJob(id=uuid.uuid4(), organization_id="org1")
    _sweep_candidates(m_objects, [job])
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
    _sweep_candidates(m_objects, [job])
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
    _sweep_candidates(m_objects, [won_job, lost_job])
    m_mark_terminal.side_effect = [True, False]

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 1}
    m_release.assert_called_once_with("org1", str(won_job.id))


# (5) no candidates -> {"swept": 0}, and no terminalize/release side effects.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
def test_sweep_with_no_candidates_is_a_pure_noop(m_objects, m_mark_terminal, m_release):
    _sweep_candidates(m_objects, [])

    resp = iv.SweepView.as_view()(_post("/x"))

    assert resp.status_code == 200
    assert resp.data == {"swept": 0}
    assert not m_mark_terminal.called
    assert not m_release.called


# ---------------------------------------------------------------------------
# TTLCleanupView
# ---------------------------------------------------------------------------


# (6) the candidate query is exactly expires_at < now AND (non-blank
# input_ref OR non-blank result_ref), oldest-expired first, capped at 500.
# This is what proves BOTH "non-expired untouched" (the expires_at__lt
# half) and "blank-ref rows excluded / second run is a no-op" (the Q half:
# a row TTLCleanupView just blanked no longer satisfies `__gt=""`).
@mock.patch.object(iv, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
def test_ttl_cleanup_queries_expired_jobs_with_a_nonblank_ref(m_objects, m_delete):
    frozen_now = timezone.now()
    m_expiry_qs = m_objects.filter.return_value
    m_ref_qs = m_expiry_qs.filter.return_value
    m_ordered_qs = m_ref_qs.order_by.return_value
    m_ordered_qs.__getitem__.return_value = []

    with mock.patch.object(iv.timezone, "now", return_value=frozen_now):
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
@mock.patch.object(iv, "delete_job_files")
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
@mock.patch.object(iv, "delete_job_files")
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
@mock.patch.object(iv, "delete_job_files")
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
@mock.patch.object(iv, "delete_job_files")
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
