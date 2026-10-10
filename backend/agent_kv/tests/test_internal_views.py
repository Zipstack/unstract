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
from agent_kv import storage  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def _post(path, body):
    return APIRequestFactory().post(path, body, format="json")


def _merge_payload(update_call):
    """Unwrap a ``stages=`` jsonb-merge expression's {stage: entry} payload.

    Also pins the expression's shape: a ``||`` (jsonb concatenation)
    ``CombinedExpression`` over the ``stages`` column, not a plain dict --
    the whole point of the DB-side merge is that ``.update()`` never
    receives a Python-computed full-column dict.
    """
    expr = update_call.kwargs["stages"]
    assert not isinstance(expr, dict), "stages must be a jsonb-merge expression"
    assert expr.connector == "||"
    assert expr.lhs.name == "stages"
    return expr.rhs.value


# ---------------------------------------------------------------------------
# _stage_merge_expression / _sanitize_counters (expression-builder unit tests)
# ---------------------------------------------------------------------------


# (u1) the expression builder produces a single-entry {stage: entry} jsonb
# merge payload over the `stages` column via the `||` connector.
def test_stage_merge_expression_builds_single_entry_jsonb_merge():
    expr = iv._stage_merge_expression("extraction", {"status": "running"})

    assert expr.connector == "||"
    assert expr.lhs.name == "stages"
    assert expr.rhs.value == {"extraction": {"status": "running"}}


# (u2) counters colliding with reserved keys are dropped.
def test_sanitize_counters_drops_reserved_keys():
    assert iv._sanitize_counters({"status": "done", "seconds": 999, "pages": 3}) == {
        "pages": 3
    }


# (u3) non-scalar counter values (dict/list) are dropped; scalars pass through.
def test_sanitize_counters_drops_non_scalar_values():
    assert iv._sanitize_counters(
        {"pages": 3, "nested": {"a": 1}, "arr": [1, 2], "ok": "yes", "flag": True}
    ) == {"pages": 3, "ok": "yes", "flag": True}


# (u4) a non-dict counters payload (e.g. a string or list) sanitizes to {}.
def test_sanitize_counters_non_dict_input_is_empty():
    assert iv._sanitize_counters("not-a-dict") == {}
    assert iv._sanitize_counters(None) == {}


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


# (1b) missing `stage` -> 400.
def test_stage_report_missing_stage_is_400():
    resp = iv.StageReportView.as_view()(
        _post("/x", {"org_id": "org1", "status": "running"}),
        job_id=uuid.uuid4(),
    )
    assert resp.status_code == 400


# (1c) missing/invalid `status` -> 400 (must be exactly "running" or "done").
def test_stage_report_invalid_status_is_400():
    resp = iv.StageReportView.as_view()(
        _post("/x", {"org_id": "org1", "stage": "extraction", "status": "bogus"}),
        job_id=uuid.uuid4(),
    )
    assert resp.status_code == 400

    resp_missing = iv.StageReportView.as_view()(
        _post("/x", {"org_id": "org1", "stage": "extraction"}),
        job_id=uuid.uuid4(),
    )
    assert resp_missing.status_code == 400


# (2) first stage report on a PENDING job flips it to RUNNING exactly once,
# and merges the stage entry via a DB-side jsonb `||` expression (not a
# plain dict) targeting only the reported stage's key.
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
    qs.update.assert_called_once()
    call = qs.update.call_args
    assert _merge_payload(call) == {"extraction": {"status": "running"}}
    assert call.kwargs["stage"] == "extraction"
    assert call.kwargs["status"] == JobStatus.RUNNING


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
    call = qs.update.call_args
    assert "status" not in call.kwargs
    assert _merge_payload(call) == {"extraction": {"status": "done", "seconds": 1.5}}


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
# entry rather than appending. With the DB-side jsonb `||` merge this falls
# out structurally: the merge payload always carries exactly one key (the
# reported stage), so the jsonb `||` operator replaces that key's value on
# the second call instead of stacking a second version alongside it.
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
    call = qs.update.call_args
    payload = _merge_payload(call)
    assert list(payload.keys()) == ["extraction"]
    assert payload == {"extraction": {"status": "done", "seconds": 2.0, "pages": 3}}
    assert call.kwargs["stage"] == "extraction"


# (5) the stage-report endpoint is the write gate for job.stages -- only the
# defined shape (status, optional seconds, sanitized flat counters) is ever
# persisted; unexpected top-level body keys (e.g. a stray "evil") must not
# leak into the stored entry.
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
    stored_entry = _merge_payload(qs.update.call_args)["extraction"]
    assert stored_entry == {"status": "running"}


# (5b) a counter named "status" or "seconds" cannot clobber the endpoint's
# own reserved fields.
@mock.patch.object(AgentKVJob, "objects")
def test_stage_report_counters_cannot_override_reserved_keys(m_jobs):
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
                "counters": {"status": "done", "seconds": 999, "pages": 3},
            },
        ),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    stored_entry = _merge_payload(qs.update.call_args)["extraction"]
    assert stored_entry == {"status": "running", "pages": 3}


# (5c) a nested-dict (or list) counter value is dropped rather than stored.
@mock.patch.object(AgentKVJob, "objects")
def test_stage_report_counters_drops_nested_values(m_jobs):
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
                "counters": {"pages": 3, "nested": {"a": 1}, "arr": [1, 2]},
            },
        ),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    stored_entry = _merge_payload(qs.update.call_args)["extraction"]
    assert stored_entry == {"status": "running", "pages": 3}


# ---------------------------------------------------------------------------
# FinalizeView
# ---------------------------------------------------------------------------


# (6) org_id missing from body -> 400.
def test_finalize_missing_org_id_is_400():
    resp = iv.FinalizeView.as_view()(_post("/x", {"success": True}), job_id=uuid.uuid4())
    assert resp.status_code == 400


# (6b) missing `success` -> 400, and no slot is released (nothing was
# finalized).
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
def test_finalize_missing_success_is_400(m_release):
    resp = iv.FinalizeView.as_view()(_post("/x", {"org_id": "org1"}), job_id=uuid.uuid4())
    assert resp.status_code == 400
    assert not m_release.called


# (6c) a non-bool `success` (e.g. a truthy string) -> 400 rather than
# silently falling through to the failure branch and persisting a FAILED
# job with an empty error.
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
def test_finalize_non_bool_success_is_400(m_release, m_mark_terminal):
    resp = iv.FinalizeView.as_view()(
        _post("/x", {"org_id": "org1", "success": "true"}), job_id=uuid.uuid4()
    )
    assert resp.status_code == 400
    assert not m_release.called
    assert not m_mark_terminal.called


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


# (7b) finalize success deletes the staged input and blanks input_ref (spec
# D10: "uploaded document deleted on job completion") -- the result file
# itself is untouched by this.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(iv, "delete_input")
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_success_deletes_input_and_blanks_ref(
    m_jobs, m_write, m_delete_input, m_mark_terminal, m_release
):
    job = AgentKVJob(
        status=JobStatus.RUNNING,
        webhook_url="",
        input_ref="org/o/agent_kv/j/input.pdf",
    )
    m_jobs.filter.return_value.first.return_value = job
    m_write.return_value = "org/o/agent_kv/j/result.json"

    job_id = uuid.uuid4()
    resp = iv.FinalizeView.as_view()(
        _post("/x", {"org_id": "org1", "success": True, "result": {}}),
        job_id=job_id,
    )

    assert resp.status_code == 200
    m_delete_input.assert_called_once_with(job)
    m_jobs.filter.return_value.update.assert_called_once_with(input_ref="")


# (7c) success finalize whose guard is LOST right after the write (e.g. a
# cancel raced in between the read and mark_terminal's guarded UPDATE) --
# the just-written result file has no ref anywhere pointing at it, so it's
# cleaned up immediately rather than orphaned forever.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(iv, "delete_result_file")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=False)
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_success_guard_loss_deletes_orphaned_result(
    m_jobs, m_write, m_mark_terminal, m_delete_result, m_release
):
    job = AgentKVJob(status=JobStatus.RUNNING, webhook_url="")
    m_jobs.filter.return_value.first.return_value = job
    m_write.return_value = "org/o/agent_kv/j/result.json"

    job_id = uuid.uuid4()
    resp = iv.FinalizeView.as_view()(
        _post(
            "/x",
            {"org_id": "org1", "success": True, "result": {"foo": "bar"}},
        ),
        job_id=job_id,
    )

    assert resp.status_code == 200
    assert resp.data["finalized"] is False
    m_delete_result.assert_called_once_with("org/o/agent_kv/j/result.json")


# (7d) success finalize that WINS the guard never deletes the result it just
# wrote -- only a guard-LOSS orphan triggers cleanup.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(iv, "delete_result_file")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(iv, "write_result")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_success_guard_win_does_not_delete_result(
    m_jobs, m_write, m_mark_terminal, m_delete_result, m_release
):
    job = AgentKVJob(status=JobStatus.RUNNING, webhook_url="")
    m_jobs.filter.return_value.first.return_value = job
    m_write.return_value = "org/o/agent_kv/j/result.json"

    iv.FinalizeView.as_view()(
        _post(
            "/x",
            {"org_id": "org1", "success": True, "result": {"foo": "bar"}},
        ),
        job_id=uuid.uuid4(),
    )

    assert not m_delete_result.called


# (7e) concurrent duplicate-SUCCESS finalize race, exercised through the REAL
# storage layer (only the object-store FileSystem is faked): two finalize
# attempts land for one job, the first WINS the terminal guard and the second
# LOSES. Because write_result now returns a UNIQUE ref per attempt, the loser
# cleans up only ITS OWN orphaned result file -- the winner's result_ref
# target is left intact (pre-Greptile critical #3: the old deterministic
# result.json path let the loser delete the winner's live result).
@mock.patch.object(storage, "FileSystem")
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal", side_effect=[True, False])
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_duplicate_success_race_loser_deletes_only_its_own_result(
    m_jobs, m_mark, m_release, m_fs
):
    # Two separate reads that both observed the job as still RUNNING (the race
    # window before either guarded UPDATE ran).
    winner_job = AgentKVJob(status=JobStatus.RUNNING, webhook_url="", input_ref="")
    loser_job = AgentKVJob(status=JobStatus.RUNNING, webhook_url="", input_ref="")
    m_jobs.filter.return_value.first.side_effect = [winner_job, loser_job]

    fh = m_fs.return_value.get_file_storage.return_value
    written: list[str] = []
    removed: list[str] = []
    fh.json_dump.side_effect = lambda path, data: written.append(path)
    fh.rm.side_effect = lambda path: removed.append(path)

    job_id = uuid.uuid4()
    body = {"org_id": "org1", "success": True, "result": {"foo": "bar"}}
    r1 = iv.FinalizeView.as_view()(_post("/x", body), job_id=job_id)  # winner
    r2 = iv.FinalizeView.as_view()(_post("/x", body), job_id=job_id)  # loser

    assert r1.data["finalized"] is True
    assert r2.data["finalized"] is False

    # Both attempts wrote a result; the two refs are DISTINCT.
    assert len(written) == 2
    assert written[0] != written[1]

    # The winner's result file (written[0]) is the one mark_terminal stored as
    # result_ref -- it must NOT be deleted. Only the loser's orphan is removed.
    assert removed == [written[1]]
    assert written[0] not in removed

    # The winner stored its OWN specific ref, not a shared deterministic path.
    winner_ref = m_mark.call_args_list[0].kwargs["result_ref"]
    assert winner_ref == written[0]


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


# (8b) duplicate finalize (guard-lost) never calls delete_input either --
# either another writer already owns cleanup, or there's nothing new to
# terminalize.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal")
@mock.patch.object(iv, "delete_input")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_duplicate_does_not_call_delete_input(
    m_jobs, m_delete_input, m_mark_terminal, m_release
):
    job = AgentKVJob(
        status=JobStatus.COMPLETED,
        webhook_url="",
        input_ref="org/o/agent_kv/j/input.pdf",
    )
    m_jobs.filter.return_value.first.return_value = job

    resp = iv.FinalizeView.as_view()(
        _post("/x", {"org_id": "org1", "success": True, "result": {}}),
        job_id=uuid.uuid4(),
    )

    assert resp.status_code == 200
    assert not m_delete_input.called
    assert not m_jobs.filter.return_value.update.called


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


# (9b) finalize failure also deletes the staged input and blanks input_ref
# -- the run is over whether it completed or failed.
@mock.patch.object(iv.AgentKVConcurrencyLimiter, "release")
@mock.patch.object(AgentKVJob, "mark_terminal", return_value=True)
@mock.patch.object(iv, "delete_input")
@mock.patch.object(AgentKVJob, "objects")
def test_finalize_failure_deletes_input_and_blanks_ref(
    m_jobs, m_delete_input, m_mark_terminal, m_release
):
    job = AgentKVJob(
        status=JobStatus.RUNNING,
        webhook_url="",
        input_ref="org/o/agent_kv/j/input.pdf",
    )
    m_jobs.filter.return_value.first.return_value = job

    job_id = uuid.uuid4()
    resp = iv.FinalizeView.as_view()(
        _post("/x", {"org_id": "org1", "success": False, "error": "boom"}),
        job_id=job_id,
    )

    assert resp.status_code == 200
    m_delete_input.assert_called_once_with(job)
    m_jobs.filter.return_value.update.assert_called_once_with(input_ref="")


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
