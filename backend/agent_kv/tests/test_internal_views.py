import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from rest_framework.test import APIRequestFactory  # noqa: E402

from agent_kv import internal_views as iv  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def _post(path, body):
    return APIRequestFactory().post(path, body, format="json")


# ---------------------------------------------------------------------------
# StageReportView
# ---------------------------------------------------------------------------


# (1) org_id missing from body -> 400 (ambient-auth views require it in body).
def test_stage_report_missing_org_id_is_400():
    resp = iv.StageReportView.as_view()(
        _post("/x", {"stage": "extraction", "status": "running"}),
        job_id=uuid.uuid4(),
    )
    assert resp.status_code == 400


# (2) first stage report on a PENDING job flips it to RUNNING exactly once,
# merges the stage entry, and sets `stage`.
@mock.patch.object(AgentKVJob, "objects")
def test_stage_report_flips_pending_to_running_once(m_jobs):
    job = AgentKVJob(status=JobStatus.PENDING, stages={})
    qs = m_jobs.filter.return_value.exclude.return_value
    qs.first.return_value = job

    resp = iv.StageReportView.as_view()(
        _post(
            "/x",
            {
                "org_id": "org1",
                "stage": "extraction",
                "status": "running",
            },
        ),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    qs.update.assert_called_once_with(
        stages={"extraction": {"status": "running"}},
        stage="extraction",
        status=JobStatus.RUNNING,
    )


# (2b) a stage report on an already-RUNNING job does NOT re-flip status --
# the "once" half of "flips RUNNING once".
@mock.patch.object(AgentKVJob, "objects")
def test_stage_report_on_running_job_does_not_touch_status(m_jobs):
    job = AgentKVJob(
        status=JobStatus.RUNNING, stages={"extraction": {"status": "running"}}
    )
    qs = m_jobs.filter.return_value.exclude.return_value
    qs.first.return_value = job

    resp = iv.StageReportView.as_view()(
        _post(
            "/x",
            {"org_id": "org1", "stage": "extraction", "status": "done", "seconds": 1.5},
        ),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    update_kwargs = qs.update.call_args.kwargs
    assert "status" not in update_kwargs


# (3) stage report on a CANCELLED (terminal) job -- the update queryset
# excludes TERMINAL, so .first() returns None -- is a 200 no-op, never
# reaching .update().
@mock.patch.object(AgentKVJob, "objects")
def test_stage_report_on_cancelled_job_is_200_noop(m_jobs):
    qs = m_jobs.filter.return_value.exclude.return_value
    qs.first.return_value = None

    resp = iv.StageReportView.as_view()(
        _post("/x", {"org_id": "org1", "stage": "extraction", "status": "running"}),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    assert not qs.update.called


# (4) duplicate stage report (same stage name posted twice) overwrites the
# entry rather than appending -- stages is a dict keyed by stage name, so
# this falls out of the merge naturally, but pin it down explicitly.
@mock.patch.object(AgentKVJob, "objects")
def test_stage_report_duplicate_overwrites_not_appends(m_jobs):
    job = AgentKVJob(
        status=JobStatus.RUNNING,
        stages={"extraction": {"status": "running"}},
    )
    qs = m_jobs.filter.return_value.exclude.return_value
    qs.first.return_value = job

    resp = iv.StageReportView.as_view()(
        _post(
            "/x",
            {
                "org_id": "org1",
                "stage": "extraction",
                "status": "done",
                "seconds": 2.0,
                "counters": {"pages": 3},
            },
        ),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    qs.update.assert_called_once_with(
        stages={"extraction": {"status": "done", "seconds": 2.0, "pages": 3}},
        stage="extraction",
    )


# (5) the stage-report endpoint is the write gate for job.stages -- only the
# defined shape (status, optional seconds, flat counters) is ever persisted;
# unexpected top-level body keys (e.g. a stray "evil") must not leak into the
# stored entry.
@mock.patch.object(AgentKVJob, "objects")
def test_stage_report_ignores_unexpected_top_level_keys(m_jobs):
    job = AgentKVJob(status=JobStatus.RUNNING, stages={})
    qs = m_jobs.filter.return_value.exclude.return_value
    qs.first.return_value = job

    resp = iv.StageReportView.as_view()(
        _post(
            "/x",
            {
                "org_id": "org1",
                "stage": "extraction",
                "status": "running",
                "evil": "payload",
                "another_bogus_key": 123,
            },
        ),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    stored_entry = qs.update.call_args.kwargs["stages"]["extraction"]
    assert stored_entry == {"status": "running"}


# ---------------------------------------------------------------------------
# FinalizeView
# ---------------------------------------------------------------------------


# (6) org_id missing from body -> 400.
def test_finalize_missing_org_id_is_400():
    resp = iv.FinalizeView.as_view()(_post("/x", {"success": True}), job_id=uuid.uuid4())
    assert resp.status_code == 400


# (7) finalize success: writes the result THEN marks the job terminal (order
# matters -- a duplicate must never rewrite a result nobody asked to change).
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_success_writes_result_then_marks_terminal(
    m_jobs, m_write, m_mark_terminal, m_release
):
    job = AgentKVJob(status=JobStatus.RUNNING, webhook_url="https://example.com/hook")
    m_jobs.filter.return_value.first.return_value = job
    m_write.return_value = "org/o/agent_kv/j/result.json"
    m_mark_terminal.return_value = True

    manager = mock.Mock()
    manager.attach_mock(m_write, "write_result")
    manager.attach_mock(m_mark_terminal, "mark_terminal")

    job_id = uuid.uuid4()
    resp = iv.FinalizeView.as_view()(
        _post(
            "/x",
            {
                "org_id": "org1",
                "success": True,
                "result": {"foo": "bar"},
                "usage_summary": {"tokens": 10},
            },
        ),
        job_id=job_id,
    )

    assert resp.status_code == 200
    assert resp.data == {
        "finalized": True,
        "webhook_url": "https://example.com/hook",
        "status": "completed",
    }
    assert [c[0] for c in manager.mock_calls] == ["write_result", "mark_terminal"]
    m_write.assert_called_once_with("org1", str(job_id), {"foo": "bar"})
    m_mark_terminal.assert_called_once_with(
        job_id,
        "org1",
        JobStatus.COMPLETED,
        result_ref="org/o/agent_kv/j/result.json",
        usage_summary={"tokens": 10},
    )


# (8) duplicate finalize: the job is already terminal (guard excludes it),
# so this is a no-op -- finalized:false and the result is NOT rewritten.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_duplicate_does_not_rewrite_result(
    m_jobs, m_write, m_mark_terminal, m_release
):
    job = AgentKVJob(status=JobStatus.COMPLETED, webhook_url="https://example.com/hook")
    m_jobs.filter.return_value.first.return_value = job

    resp = iv.FinalizeView.as_view()(
        _post("/x", {"org_id": "org1", "success": True, "result": {"foo": "bar"}}),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    assert resp.data == {
        "finalized": False,
        "webhook_url": "https://example.com/hook",
        "status": "completed",
    }
    assert not m_write.called
    assert not m_mark_terminal.called


# (9) finalize failure records the error via mark_terminal(FAILED, ...).
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_failure_records_error(m_jobs, m_write, m_mark_terminal, m_release):
    job = AgentKVJob(status=JobStatus.RUNNING, webhook_url="")
    m_jobs.filter.return_value.first.return_value = job
    m_mark_terminal.return_value = True

    job_id = uuid.uuid4()
    resp = iv.FinalizeView.as_view()(
        _post(
            "/x",
            {"org_id": "org1", "success": False, "error": "LLM provider timed out"},
        ),
        job_id=job_id,
    )

    assert resp.status_code == 200
    assert resp.data == {"finalized": True, "webhook_url": "", "status": "failed"}
    assert not m_write.called
    m_mark_terminal.assert_called_once_with(
        job_id, "org1", JobStatus.FAILED, error="LLM provider timed out"
    )


# (10) the concurrency slot is released on every finalize path -- including
# when the write/finalize work raises -- because release() sits in a
# finally.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_releases_slot_even_when_write_result_raises(
    m_jobs, m_write, m_mark_terminal, m_release
):
    job = AgentKVJob(status=JobStatus.RUNNING, webhook_url="")
    m_jobs.filter.return_value.first.return_value = job
    m_write.side_effect = RuntimeError("storage exploded")

    job_id = uuid.uuid4()
    try:
        iv.FinalizeView.as_view()(
            _post("/x", {"org_id": "org1", "success": True, "result": {}}),
            job_id=job_id,
        )
    except RuntimeError:
        pass

    m_release.assert_called_once_with("org1", str(job_id))
    assert not m_mark_terminal.called


# (10b) slot released on the duplicate (already-terminal, no-op) path too.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_releases_slot_on_duplicate_noop_path(
    m_jobs, m_write, m_mark_terminal, m_release
):
    job = AgentKVJob(status=JobStatus.CANCELLED, webhook_url="")
    m_jobs.filter.return_value.first.return_value = job

    job_id = uuid.uuid4()
    iv.FinalizeView.as_view()(
        _post("/x", {"org_id": "org1", "success": False, "error": "late"}),
        job_id=job_id,
    )

    m_release.assert_called_once_with("org1", str(job_id))


# ---------------------------------------------------------------------------
# URL wiring
# ---------------------------------------------------------------------------


# (11) regression pin for the frozen paths (spec Interfaces block): the
# cloud executor calls these exact URLs, so a dropped/renamed include in
# internal_base_urls.py must fail loudly here rather than 404 in prod.
def test_frozen_internal_urls_resolve_to_the_right_views():
    from django.urls import resolve

    job_id = uuid.uuid4()
    stage = resolve(f"/internal/v1/agent-kv/jobs/{job_id}/stage/")
    assert stage.func.cls is iv.StageReportView
    assert stage.kwargs == {"job_id": job_id}

    finalize = resolve(f"/internal/v1/agent-kv/jobs/{job_id}/finalize/")
    assert finalize.func.cls is iv.FinalizeView
    assert finalize.kwargs == {"job_id": job_id}
