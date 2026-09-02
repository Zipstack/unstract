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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    assert resp.data["status"] == "running"
    assert resp.data["stage"] == "extraction"
    # STAGE_NAMES order is document_processing, extraction, ... -- "qa" and
    # every other configured stage name is absent from job.stages, so only
    # these two appear, in that order.
    assert [s["name"] for s in resp.data["stages"]] == [
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        result_ref="org/o/agent_kv/j/result.json",
        expires_at=timezone.now() + timedelta(days=1),
    )
    m_jobs.get.return_value = job

    resp = ev.JobResultView.as_view()(_authed(), job_id=uuid.uuid4())

    assert resp.status_code == 200
    assert resp.data == {"success": True, "fields": {}}
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        input_ref="org/o/agent_kv/j/input.pdf",
        result_ref="org/o/agent_kv/j/result.json",
    )
    m_jobs.get.return_value = job

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    m_delete_files.assert_called_once_with(job)
    assert job.input_ref == ""
    assert job.result_ref == ""
    assert m_save.called


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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    job = AgentKVJob(status=JobStatus.RUNNING)
    job.organization_id = "org1"
    m_jobs.get.return_value = job

    manager = mock.Mock()
    manager.attach_mock(m_mark_terminal, "mark_terminal")
    manager.attach_mock(m_delete_files, "delete_job_files")

    resp = ev.JobDeleteView.as_view()(_authed(method="delete"), job_id=uuid.uuid4())

    assert resp.status_code == 204
    m_mark_terminal.assert_called_once_with(job.id, "org1", JobStatus.CANCELLED)
    m_delete_files.assert_called_once_with(job)
    assert [c[0] for c in manager.mock_calls] == ["mark_terminal", "delete_job_files"]


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
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
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
