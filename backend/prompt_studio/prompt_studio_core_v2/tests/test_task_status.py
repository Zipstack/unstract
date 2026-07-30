"""UN-3693: PromptStudioCoreView.task_status — flag-gated.

Gate on the per-org ``pg_queue_enabled`` flag (the same the executor dispatch uses):
flag ON → read ``pg_task_result`` (completed / failed / none→processing); flag OFF
(default) → Celery ``AsyncResult`` unchanged, and the PG table is never queried on
the hot poll path. ``check_feature_flag_status`` already fails closed to ``False`` on
any Flipt error, so "flag off / Flipt down" is one path. A transient PG DB error
degrades to "processing", not a bare 500.

NOTE: run via a Django-bootstrapped harness (no pytest-django in this repo yet — the
CI-gating of these view tests is tracked in UN-3692). Verified locally green.
"""

from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

_VIEWS = "prompt_studio.prompt_studio_core_v2.views"
_TID = "task-abc"


def _view():
    view = PromptStudioCoreView()
    view.get_object = MagicMock()  # bypass permission/object lookup
    return view


def _flag(enabled):
    return patch(f"{_VIEWS}.check_feature_flag_status", return_value=enabled)


def _org():
    return patch(f"{_VIEWS}.UserSessionUtils.get_organization_id", return_value="org1")


def _stub_pg(pg_row=None, *, error=None):
    """Patch pg_task_result read: .filter().values().first() → pg_row, or raise."""
    m = MagicMock()
    if error is not None:
        m.objects.filter.side_effect = error
    else:
        m.objects.filter.return_value.values.return_value.first.return_value = pg_row
    return patch("pg_queue.models.PgTaskResult", m), m


def _async(ready, successful=True, result=""):
    ar = MagicMock()
    ar.return_value.ready.return_value = ready
    ar.return_value.successful.return_value = successful
    ar.return_value.result = result
    return ar


class TestTaskStatusFlagOn:
    def test_pg_completed(self):
        p_pg, _ = _stub_pg({"status": "completed", "error": ""})
        with _org(), _flag(True), p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "completed"}

    def test_pg_failed(self):
        p_pg, _ = _stub_pg({"status": "failed", "error": "extraction blew up"})
        with _org(), _flag(True), p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data["status"] == "failed"
        assert resp.data["error"] == "extraction blew up"
        assert resp.status_code == 500

    def test_no_pg_row_is_processing(self):
        p_pg, _ = _stub_pg(None)  # PG task not done yet — no "pending" row
        with _org(), _flag(True), p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "processing"}

    def test_pg_db_error_degrades_to_processing(self):
        # A transient PG read error must not 500; degrade to "processing".
        p_pg, _ = _stub_pg(error=RuntimeError("db blip"))
        with _org(), _flag(True), p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "processing"}


class TestTaskStatusFlagOff:
    def test_celery_completed_never_queries_pg(self):
        # flag off (also the Flipt-error fail-closed path): Celery + PG untouched.
        p_pg, pg = _stub_pg({"status": "completed"})  # would resolve, if queried
        with _org(), _flag(False), p_pg, patch(f"{_VIEWS}.AsyncResult", _async(ready=True)):
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "completed"}
        pg.objects.filter.assert_not_called()  # default path never touches PG

    def test_celery_failed(self):
        with _org(), _flag(False), patch(
            f"{_VIEWS}.AsyncResult", _async(ready=True, successful=False, result="celery boom")
        ):
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data["status"] == "failed"
        assert "celery boom" in resp.data["error"]
        assert resp.status_code == 500

    def test_pending(self):
        with _org(), _flag(False), patch(f"{_VIEWS}.AsyncResult", _async(ready=False)):
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "processing"}
