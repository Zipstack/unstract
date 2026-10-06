import os
import uuid
from datetime import timedelta
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.utils import timezone  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from agent_kv import execution_views as ev  # noqa: E402
from agent_kv import execution_views_result as evr  # noqa: E402
from agent_kv.models import AgentKVJob, AgentKVKey, JobStatus  # noqa: E402
from agent_kv.tests._factories import kv_key  # noqa: E402


def _authed(method="get", path="/agent-kv/x"):
    req = getattr(APIRequestFactory(), method)(path)
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    return req


# ---------------------------------------------------------------------------
# (1) status for foreign-org job -> 404 (indistinguishable from unknown).
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_foreign_org_job_is_404(m_keys, m_jobs):
    m_keys.get.return_value = kv_key()
    m_jobs.get.side_effect = AgentKVJob.DoesNotExist
    resp = ev.JobStatusView.as_view()(_authed(), job_id=uuid.uuid4())
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# (2) status running -> stages list ordered per STAGE_NAMES, lowercased
# status, only the stages actually present are included.
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_status_running_builds_ordered_stages_and_lowercases_status(m_keys, m_jobs):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.RUNNING,
        stage="extraction",
        stages={
            "extraction": {"status": "running"},
            "document_processing": {"status": "done", "seconds": 0.5},
        },
        pages_total=3,
    )
    job.created_at = timezone.now()
    m_jobs.get.return_value = job

    resp = ev.JobStatusView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 200
    # `status` is the JOB's, so it stays top level; stage reporting is
    # extractor-scoped (spec §7.2).
    assert resp.data["status"] == "running"
    kv = resp.data["extractors"]["kv"]
    assert kv["stage"] == "extraction"
    # STAGE_NAMES order is document_processing, extraction, ... -- "qa" and
    # every other configured stage name is absent from job.stages, so only
    # these two appear, in that order.
    assert [s["name"] for s in kv["stages"]] == [
        "document_processing",
        "extraction",
    ]
    assert resp.data["pages_total"] == 3
    assert "error" not in resp.data


# ---------------------------------------------------------------------------
# (3) result before completion (non-terminal, e.g. RUNNING) -> 409 with the
# current status, lowercased (spec §7.3 controller ruling).
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_result_before_completion_is_409_with_current_status(m_keys, m_jobs):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.RUNNING)
    m_jobs.get.return_value = job

    resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 409
    assert resp.data == {"status": "running"}


# ---------------------------------------------------------------------------
# (4) result after expires_at -> 404.
# ---------------------------------------------------------------------------
@mock.patch.object(evr, "read_result")
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_result_after_expiry_is_404(m_keys, m_jobs, m_read):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        result_ref="org/o/agent_kv/j/result.json",
        expires_at=timezone.now() - timedelta(days=1),
    )
    m_jobs.get.return_value = job

    resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 404
    assert not m_read.called


# ---------------------------------------------------------------------------
# (5) result happy path -> returns read_result payload unchanged.
# ---------------------------------------------------------------------------
@mock.patch.object(evr, "read_result", return_value={"success": True, "fields": {}})
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_result_happy_path_returns_read_result_payload(m_keys, m_jobs, m_read):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        result_ref="org/o/agent_kv/j/result.json",
        expires_at=timezone.now() + timedelta(days=1),
    )
    m_jobs.get.return_value = job

    resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 200
    # The stored blob is the engine's own result; the response namespaces it
    # per extractor and adds per-extractor usage attribution (spec §7.3).
    # `success`/`status` at top level on every terminal payload, so a client
    # branches the same way for completed, failed and cancelled.
    assert resp.data["success"] is True
    assert resp.data["status"] == "completed"
    assert resp.data["extractors"] == {"kv": {"success": True, "fields": {}}}
    assert set(resp.data["usage_summary"]) == {"total", "by_extractor"}
    assert list(resp.data["usage_summary"]["by_extractor"]) == ["kv"]
    m_read.assert_called_once_with(job.result_ref)


# ---------------------------------------------------------------------------
# (5b) result for a FAILED job -> 200 with a success:false body carrying the
# job's own (user-safe) error -- spec §7.3: "Failed jobs: {success: false,
# error, timing} with a user-safe error". This also covers the SubmitView
# sync-wait fix: that branch reuses this exact function unconditionally for
# any terminal job, so it now gets a correct 200 body instead of a 404.
# ---------------------------------------------------------------------------
@mock.patch.object(evr, "read_result")
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_result_for_failed_job_is_200_with_success_false_and_error(
    m_keys, m_jobs, m_read
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.FAILED,
        error="LLM provider timed out",
        expires_at=timezone.now() + timedelta(days=1),
    )
    m_jobs.get.return_value = job

    resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 200
    assert resp.data == {
        "success": False,
        "status": "failed",
        "error": "LLM provider timed out",
    }
    assert not m_read.called


# ---------------------------------------------------------------------------
# (5c) result for a CANCELLED job -> 200 with a fixed success:false/cancelled
# body (spec §7.3 controller ruling).
# ---------------------------------------------------------------------------
@mock.patch.object(evr, "read_result")
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_result_for_cancelled_job_is_200_with_cancelled_body(m_keys, m_jobs, m_read):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.CANCELLED,
        expires_at=timezone.now() + timedelta(days=1),
    )
    m_jobs.get.return_value = job

    resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 200
    assert resp.data == {"success": False, "status": "cancelled"}
    assert not m_read.called


# ---------------------------------------------------------------------------
# (5d) result for a COMPLETED job with a blank result_ref (files already
# swept by TTL cleanup, row not yet expired) -> 404, same as the expired
# case -- exercises the new blank-ref branch distinctly from expiry.
# ---------------------------------------------------------------------------
@mock.patch.object(evr, "read_result")
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_result_completed_with_blank_ref_is_404(m_keys, m_jobs, m_read):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        result_ref="",
        expires_at=timezone.now() + timedelta(days=1),
    )
    m_jobs.get.return_value = job

    resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 404
    assert not m_read.called


# ---------------------------------------------------------------------------
# (6) cancel on RUNNING -> mark_terminal called with CANCELLED, 200.
# ---------------------------------------------------------------------------
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_cancel_on_running_marks_terminal_and_200s(
    m_keys, m_jobs, m_mark_terminal, m_release
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.RUNNING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    resp = ev.JobCancelView.as_view()(_authed(method="post"), job_id=uuid.uuid4())

    assert resp.status_code == 200
    assert resp.data == {"status": "cancelled"}
    m_mark_terminal.assert_called_once_with(
        job.id, job.organization_id, JobStatus.CANCELLED
    )


# ---------------------------------------------------------------------------
# (6b) cancel that WINS the terminal guard releases the concurrency slot --
# a job cancelled BEFORE dispatch gets no finalize callback and the sweep's
# phase-1 only targets PENDING (not CANCELLED), so without this its slot
# would leak until the 6h TTL (pre-Greptile important #4). release() is
# idempotent (zrem), so a later finalize-callback release is harmless.
# ---------------------------------------------------------------------------
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_cancel_win_releases_concurrency_slot(m_keys, m_jobs, m_mark_terminal, m_release):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.PENDING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    resp = ev.JobCancelView.as_view()(_authed(method="post"), job_id=uuid.uuid4())

    assert resp.status_code == 200
    m_release.assert_called_once_with("org1", str(job.id))


# ---------------------------------------------------------------------------
# (6c) cancel that LOSES the guard (job already terminal) must NOT release --
# whoever terminalized it (finalize callback / a prior cancel) owns the slot.
# ---------------------------------------------------------------------------
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=False)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_cancel_loss_does_not_release_slot(m_keys, m_jobs, m_mark_terminal, m_release):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.COMPLETED)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    resp = ev.JobCancelView.as_view()(_authed(method="post"), job_id=uuid.uuid4())

    assert resp.status_code == 409
    assert not m_release.called


# ---------------------------------------------------------------------------
# (7) cancel on COMPLETED -> 409 with current status; result untouched
# (the guard lost, so nothing about the stored result is read or written).
# ---------------------------------------------------------------------------
@mock.patch.object(evr, "read_result")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=False)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_cancel_on_completed_is_409_and_result_untouched(
    m_keys, m_jobs, m_mark_terminal, m_read
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.COMPLETED)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    resp = ev.JobCancelView.as_view()(_authed(method="post"), job_id=uuid.uuid4())

    assert resp.status_code == 409
    # Status is lowercased consistently across every endpoint (spec §7.2) --
    # the 409 body used to leak the raw uppercase value (pre-Greptile #5).
    assert resp.data == {"status": "completed"}
    assert m_mark_terminal.called
    assert not m_read.called


# ---------------------------------------------------------------------------
# (8) delete calls delete_job_files and blanks both refs.
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_calls_delete_job_files_and_blanks_refs(
    m_keys, m_jobs, m_delete_files, m_save
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        input_ref="org/o/agent_kv/j/input.pdf",
        result_ref="org/o/agent_kv/j/result.json",
    )
    m_jobs.get.return_value = job
    m_delete_files.return_value = ["input_ref", "result_ref"]

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    m_delete_files.assert_called_once_with(job)
    assert job.input_ref == ""
    assert job.result_ref == ""
    # update_fields carries exactly the blanked refs, so a ref left set is not
    # written back as "" by a wider save().
    assert m_save.call_args.kwargs["update_fields"] == ["input_ref", "result_ref"]


# ---------------------------------------------------------------------------
# (8b) delete on a non-terminal (RUNNING) job cancels it FIRST, before the
# files are deleted -- a still-running job that finalizes late would
# otherwise write a fresh result onto a job the caller just deleted.
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "delete_job_files")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_on_running_job_cancels_before_deleting_files(
    m_keys, m_jobs, m_mark_terminal, m_delete_files, m_save
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.RUNNING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job
    m_delete_files.return_value = ["input_ref", "result_ref"]

    manager = mock.Mock()
    manager.attach_mock(m_mark_terminal, "mark_terminal")
    manager.attach_mock(m_delete_files, "delete_job_files")

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    m_mark_terminal.assert_called_once_with(job.id, "org1", JobStatus.CANCELLED)
    m_delete_files.assert_called_once_with(job)
    assert [c[0] for c in manager.mock_calls] == ["mark_terminal", "delete_job_files"]


# ---------------------------------------------------------------------------
# (8e) DELETE on an in-flight job RELEASES the concurrency slot, exactly as
# JobCancelView does (Greptile review #2). The slot is taken at submit and
# released by _fail_job_response, the finalize callback and the sweep -- a job
# terminalized here before dispatch hits none of those, and the sweep's phase-1
# only targets PENDING, never CANCELLED. Without the release each such delete
# leaked a slot until the 6h TTL, and enough of them exhaust the org's
# allowance and start rejecting new submits.
# ---------------------------------------------------------------------------
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "delete_job_files", return_value=["input_ref", "result_ref"])
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_on_running_job_releases_the_concurrency_slot(
    m_keys, m_jobs, m_mark_terminal, m_delete_files, m_save, m_release
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.RUNNING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    m_release.assert_called_once_with("org1", str(job.id))


# ---------------------------------------------------------------------------
# (8f) ...but only when THIS request won the terminal-state race. A concurrent
# cancel or finalize that terminalized first is the one accounting for the
# slot; releasing on a lost race would hand a slot back twice.
# ---------------------------------------------------------------------------
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "save")
# A lost race re-reads the row before cleanup (see 8i); this suite touches no
# database, so the read itself is stubbed out here.
@mock.patch.object(AgentKVJob, "refresh_from_db")
@mock.patch.object(ev, "delete_job_files", return_value=["input_ref", "result_ref"])
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=False)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_does_not_release_the_slot_when_it_loses_the_terminal_race(
    m_keys, m_jobs, m_mark_terminal, m_delete_files, m_refresh, m_save, m_release
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.RUNNING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    assert not m_release.called


# ---------------------------------------------------------------------------
# (8g) a ref whose file could NOT be deleted is left set (Greptile review #3).
# It is the only handle TTL cleanup can retry from: its candidate query matches
# rows by `input_ref > "" OR result_ref > ""`, so blanking a ref whose object is
# still in the bucket orphans that object permanently. Still 204 -- the job is
# terminal and the caller's intent is recorded.
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "delete_job_files")
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_keeps_the_ref_whose_file_delete_failed(
    m_keys, m_jobs, m_delete_files, m_save
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        input_ref="org/o/agent_kv/j/input.pdf",
        result_ref="org/o/agent_kv/j/result.json",
    )
    m_jobs.get.return_value = job
    # Input gone; the result delete raised inside delete_job_files.
    m_delete_files.return_value = ["input_ref"]

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    assert job.input_ref == ""
    assert job.result_ref == "org/o/agent_kv/j/result.json"
    assert m_save.call_args.kwargs["update_fields"] == ["input_ref"]


# ---------------------------------------------------------------------------
# (8c) delete on an already-terminal job never attempts to cancel it again --
# unchanged behavior for the terminal case.
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "delete_job_files")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_on_terminal_job_does_not_call_mark_terminal(
    m_keys, m_jobs, m_mark_terminal, m_delete_files, m_save
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.COMPLETED)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    assert not m_mark_terminal.called
    m_delete_files.assert_called_once_with(job)


# ---------------------------------------------------------------------------
# (9) every job-scoped endpoint 401s (403, per Forbidden.status_code)
# without a key (spec §6.8 regression).
#
# The brief's shown snippet for this test wraps the call in
# ``pytest.raises(Forbidden)``, mirroring test_auth.py -- but that suite
# calls the ``@validate_api_key``-decorated function directly, bypassing
# DRF's dispatch(). Routed through the real ``.as_view()()`` cycle (as here,
# and as every other view in this module is exercised), DRF's dispatch()
# catches the raised ``Forbidden`` (an APIException) via
# ``drf_standardized_errors``'s exception handler and renders it as a normal
# Response -- exactly like ``test_foreign_org_job_is_404`` above asserts
# ``resp.status_code`` for ``JobNotFound`` rather than expecting a raise.
# Verified empirically (see task-9-report.md); asserting the response here
# instead keeps the same regression coverage without a spurious failure.
# ---------------------------------------------------------------------------
def test_all_job_views_401_without_key():
    for view, method in [
        (ev.JobStatusView, "get"),
        (ev.JobResultView, "get"),
        (ev.JobCancelView, "post"),
        (ev.JobDeleteView, "delete"),
    ]:
        req = getattr(APIRequestFactory(), method)("/agent-kv/x")
        resp = view.as_view()(req, job_id=uuid.uuid4())
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# (8i) Losing the terminal race must RE-READ the job before touching its files.
#
# The race: DELETE reads a RUNNING job (result_ref ""), the finalize callback
# wins the guarded UPDATE in between and writes COMPLETED + a real result_ref,
# and `mark_terminal` here returns False. Without a refresh the cleanup below
# runs against the stale copy: `delete_job_files` reports an already-empty
# `result_ref` as "cleared" (there was nothing to delete), and the save then
# writes "" OVER the winner's real ref. The job stays COMPLETED, its result
# 404s, and the object is orphaned -- TTL cleanup selects on `result_ref > ""`,
# so a blanked row never comes back.
#
# Reported by Greptile on PR #2317.
# ---------------------------------------------------------------------------
@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "delete_job_files")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=False)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_refreshes_the_job_when_it_loses_the_terminal_race(
    m_keys, m_jobs, m_mark_terminal, m_delete_files, m_save, m_release
):
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.RUNNING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    # The winner's write, applied by refresh_from_db: COMPLETED + a real ref.
    def _win_the_race():
        job.status = JobStatus.COMPLETED
        job.result_ref = "org1/job/result.json"

    with mock.patch.object(
        AgentKVJob, "refresh_from_db", side_effect=_win_the_race
    ) as m_refresh:
        # Capture what the cleanup actually SAW. `call_args` would be useless
        # here: it records a reference to the same job object the view then
        # blanks, so by assertion time it reads "" whether the fix works or not.
        seen: list[str] = []

        def _record(j):
            seen.append(j.result_ref)
            return ["input_ref", "result_ref"] if j.result_ref else ["input_ref"]

        m_delete_files.side_effect = _record
        resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    assert m_refresh.called, (
        "a lost terminal race must re-read the job; acting on the stale copy "
        "blanks the winner's result_ref and orphans the result file"
    )
    # The file helper saw the winner's ref, so the real object is deleted...
    assert seen == ["org1/job/result.json"]
    # ...and the blanking is of a ref that was genuinely cleared, not a stale "".
    assert m_save.call_args.kwargs["update_fields"] == ["input_ref", "result_ref"]


@mock.patch.object(ev.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "save")
@mock.patch.object(ev, "delete_job_files", return_value=["input_ref", "result_ref"])
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_delete_does_not_refresh_when_it_wins_the_terminal_race(
    m_keys, m_jobs, m_mark_terminal, m_delete_files, m_save, m_release
):
    """Winning means nothing else wrote to the row, so the in-memory copy is
    current and the extra query would be waste on the common path.
    """
    m_keys.get.return_value = kv_key()
    job = AgentKVJob(status=JobStatus.RUNNING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    with mock.patch.object(AgentKVJob, "refresh_from_db") as m_refresh:
        resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    assert not m_refresh.called
