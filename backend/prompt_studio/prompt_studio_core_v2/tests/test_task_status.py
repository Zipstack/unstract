"""UN-3693 / UN-4046: PromptStudioCoreView.task_status.

The task rode PG, so status is read from ``pg_task_result``: completed / failed /
no row → processing. A transient PG DB error degrades to "processing", not a bare
500 — a status-code-keyed client would misread a 500 as a terminal task failure.

This used to be gated on the per-org ``pg_queue_enabled`` flag, with a Celery
``AsyncResult`` fall-through when it was off. The flag is gone (UN-4046), so the
flag-off suite went with it — there is no Celery result backend to poll (the eager
PG executor never wrote one, which is why the gate existed at all).

NOTE: run via a Django-bootstrapped harness (no pytest-django in this repo yet — the
CI-gating of these view tests is tracked in UN-3692). Verified locally green.
"""

from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

_TID = "task-abc"


def _view():
    view = PromptStudioCoreView()
    view.get_object = MagicMock()  # bypass permission/object lookup
    return view


def _stub_pg(pg_row=None, *, error=None):
    """Patch pg_task_result read: .filter().values().first() → pg_row, or raise."""
    m = MagicMock()
    if error is not None:
        m.objects.filter.side_effect = error
    else:
        m.objects.filter.return_value.values.return_value.first.return_value = pg_row
    return patch("pg_queue.models.PgTaskResult", m), m


class TestTaskStatus:
    def test_completed(self):
        p_pg, _ = _stub_pg({"status": "completed", "error": ""})
        with p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "completed"}

    def test_failed(self):
        p_pg, _ = _stub_pg({"status": "failed", "error": "extraction blew up"})
        with p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data["status"] == "failed"
        assert resp.data["error"] == "extraction blew up"
        assert resp.status_code == 500

    def test_no_row_is_processing(self):
        p_pg, _ = _stub_pg(None)  # PG task not done yet — no "pending" row
        with p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "processing"}

    def test_db_error_degrades_to_processing(self):
        # A transient PG read error must not 500; degrade to "processing".
        p_pg, _ = _stub_pg(error=RuntimeError("db blip"))
        with p_pg:
            resp = _view().task_status(MagicMock(), task_id=_TID)
        assert resp.data == {"task_id": _TID, "status": "processing"}
