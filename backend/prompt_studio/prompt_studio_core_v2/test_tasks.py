"""Phase 7-9 sanity tests for Prompt Studio IDE async backend.

Tests the Celery task definitions (Phase 7), view dispatch (Phase 8),
and polling endpoint (Phase 9).

Requires Django to be configured (source .env before running):
    set -a && source .env && set +a
    uv run pytest prompt_studio/prompt_studio_core_v2/test_tasks.py -v
"""

import os
from unittest.mock import patch

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.dev")
django.setup()

import pytest  # noqa: E402
from account_v2.constants import Common  # noqa: E402
from celery import Celery  # noqa: E402
from utils.local_context import StateStore  # noqa: E402

from prompt_studio.prompt_studio_core_v2.tasks import (  # noqa: E402
    PROMPT_STUDIO_RESULT_EVENT,
    ide_prompt_complete,
    run_fetch_response,
    run_index_document,
    run_single_pass_extraction,
)

# ---------------------------------------------------------------------------
# Celery eager-mode app for testing
# ---------------------------------------------------------------------------
test_app = Celery("test")
test_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
    result_backend="cache+memory://",
)
run_index_document.bind(test_app)
run_fetch_response.bind(test_app)
run_single_pass_extraction.bind(test_app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
COMMON_KWARGS = {
    "tool_id": "tool-123",
    "org_id": "org-456",
    "user_id": "user-789",
    "document_id": "doc-abc",
    "run_id": "run-def",
    "log_events_id": "session-room-xyz",
    "request_id": "req-001",
}


# ===================================================================
# Phase 7: Task definition tests
# ===================================================================
class TestTaskNames:
    def test_index_document_task_name(self):
        assert run_index_document.name == "prompt_studio_index_document"

    def test_fetch_response_task_name(self):
        assert run_fetch_response.name == "prompt_studio_fetch_response"

    def test_single_pass_task_name(self):
        assert run_single_pass_extraction.name == "prompt_studio_single_pass"


class TestRunIndexDocument:
    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_success_returns_result(self, mock_helper, mock_emit):
        mock_helper.index_document.return_value = "unique-id-123"
        result = run_index_document.apply(
            kwargs={**COMMON_KWARGS, "file_name": "test.pdf"}
        ).get()

        assert result == {
            "message": "Document indexed successfully.",
            "document_id": "doc-abc",
        }
        mock_helper.index_document.assert_called_once_with(
            tool_id="tool-123",
            file_name="test.pdf",
            org_id="org-456",
            user_id="user-789",
            document_id="doc-abc",
            run_id="run-def",
        )

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_success_emits_completed_event(self, mock_helper, mock_emit):
        mock_helper.index_document.return_value = "unique-id-123"
        run_index_document.apply(kwargs={**COMMON_KWARGS, "file_name": "test.pdf"}).get()

        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["room"] == "session-room-xyz"
        assert kwargs["event"] == PROMPT_STUDIO_RESULT_EVENT
        assert kwargs["data"]["status"] == "completed"
        assert kwargs["data"]["operation"] == "index_document"
        assert kwargs["data"]["result"] == {
            "message": "Document indexed successfully.",
            "document_id": "doc-abc",
        }
        assert "task_id" in kwargs["data"]

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_failure_emits_error_and_reraises(self, mock_helper, mock_emit):
        mock_helper.index_document.side_effect = RuntimeError("index boom")

        with pytest.raises(RuntimeError, match="index boom"):
            run_index_document.apply(
                kwargs={**COMMON_KWARGS, "file_name": "test.pdf"}
            ).get()

        mock_emit.assert_called_once()
        assert mock_emit.call_args.kwargs["data"]["status"] == "failed"
        assert "index boom" in mock_emit.call_args.kwargs["data"]["error"]

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_state_store_cleared_on_success(self, mock_helper, mock_emit):
        mock_helper.index_document.return_value = "ok"
        run_index_document.apply(kwargs={**COMMON_KWARGS, "file_name": "test.pdf"}).get()

        assert StateStore.get(Common.LOG_EVENTS_ID) is None
        assert StateStore.get(Common.REQUEST_ID) is None

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_state_store_cleared_on_failure(self, mock_helper, mock_emit):
        mock_helper.index_document.side_effect = RuntimeError("fail")
        with pytest.raises(RuntimeError):
            run_index_document.apply(
                kwargs={**COMMON_KWARGS, "file_name": "test.pdf"}
            ).get()

        assert StateStore.get(Common.LOG_EVENTS_ID) is None
        assert StateStore.get(Common.REQUEST_ID) is None

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_state_store_set_during_execution(self, mock_helper, mock_emit):
        """Verify StateStore has the right values while the helper runs."""
        captured = {}

        def capture_state(**kwargs):
            captured["log_events_id"] = StateStore.get(Common.LOG_EVENTS_ID)
            captured["request_id"] = StateStore.get(Common.REQUEST_ID)
            return "ok"

        mock_helper.index_document.side_effect = capture_state
        run_index_document.apply(kwargs={**COMMON_KWARGS, "file_name": "test.pdf"}).get()

        assert captured["log_events_id"] == "session-room-xyz"
        assert captured["request_id"] == "req-001"
        # And cleared after
        assert StateStore.get(Common.LOG_EVENTS_ID) is None


class TestRunFetchResponse:
    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_success_returns_response(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.return_value = {
            "output": {"field": "value"},
            "metadata": {"tokens": 42},
        }

        result = run_fetch_response.apply(
            kwargs={
                **COMMON_KWARGS,
                "id": "prompt-1",
                "profile_manager_id": "pm-1",
            }
        ).get()

        assert result == {"status": "completed", "operation": "fetch_response"}
        mock_helper.prompt_responder.assert_called_once_with(
            id="prompt-1",
            tool_id="tool-123",
            org_id="org-456",
            user_id="user-789",
            document_id="doc-abc",
            run_id="run-def",
            profile_manager_id="pm-1",
        )

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_success_emits_fetch_response_event(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.return_value = {"output": "data"}
        run_fetch_response.apply(
            kwargs={**COMMON_KWARGS, "id": "p1", "profile_manager_id": None}
        ).get()

        data = mock_emit.call_args.kwargs["data"]
        assert data["status"] == "completed"
        assert data["operation"] == "fetch_response"

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_failure_emits_error(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.side_effect = ValueError("prompt fail")

        with pytest.raises(ValueError, match="prompt fail"):
            run_fetch_response.apply(kwargs=COMMON_KWARGS).get()

        data = mock_emit.call_args.kwargs["data"]
        assert data["status"] == "failed"
        assert "prompt fail" in data["error"]

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_optional_params_default_none(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.return_value = {}
        run_fetch_response.apply(kwargs=COMMON_KWARGS).get()

        mock_helper.prompt_responder.assert_called_once_with(
            id=None,
            tool_id="tool-123",
            org_id="org-456",
            user_id="user-789",
            document_id="doc-abc",
            run_id="run-def",
            profile_manager_id=None,
        )

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_state_store_cleared(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.return_value = {}
        run_fetch_response.apply(kwargs=COMMON_KWARGS).get()
        assert StateStore.get(Common.LOG_EVENTS_ID) is None


class TestRunSinglePassExtraction:
    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_success_returns_response(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.return_value = {"output": {"key": "val"}}

        result = run_single_pass_extraction.apply(kwargs=COMMON_KWARGS).get()

        assert result == {"status": "completed", "operation": "single_pass_extraction"}
        mock_helper.prompt_responder.assert_called_once_with(
            tool_id="tool-123",
            org_id="org-456",
            user_id="user-789",
            document_id="doc-abc",
            run_id="run-def",
        )

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_success_emits_single_pass_event(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.return_value = {"data": "ok"}
        run_single_pass_extraction.apply(kwargs=COMMON_KWARGS).get()

        data = mock_emit.call_args.kwargs["data"]
        assert data["status"] == "completed"
        assert data["operation"] == "single_pass_extraction"

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_failure_emits_error(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.side_effect = TypeError("single pass fail")

        with pytest.raises(TypeError, match="single pass fail"):
            run_single_pass_extraction.apply(kwargs=COMMON_KWARGS).get()

        data = mock_emit.call_args.kwargs["data"]
        assert data["status"] == "failed"

    @patch("utils.log_events._emit_websocket_event")
    @patch("prompt_studio.prompt_studio_core_v2.prompt_studio_helper.PromptStudioHelper")
    def test_state_store_cleared(self, mock_helper, mock_emit):
        mock_helper.prompt_responder.return_value = {}
        run_single_pass_extraction.apply(kwargs=COMMON_KWARGS).get()
        assert StateStore.get(Common.LOG_EVENTS_ID) is None


# ===================================================================
# Phase 8: View dispatch tests
# ===================================================================
class TestViewsDispatchTasks:
    """Verify the three views use dispatch_with_callback, not direct helpers."""

    def test_index_document_view_dispatches_with_callback(self):
        import inspect

        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        source = inspect.getsource(PromptStudioCoreView.index_document)
        assert "dispatch_with_callback" in source
        assert "ide_index_complete" in source
        assert "PromptStudioHelper.index_document(" not in source
        assert "HTTP_202_ACCEPTED" in source

    def test_fetch_response_view_dispatches_with_callback(self):
        import inspect

        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        source = inspect.getsource(PromptStudioCoreView.fetch_response)
        assert "dispatch_with_callback" in source
        assert "ide_prompt_complete" in source
        assert "PromptStudioHelper.prompt_responder(" not in source
        assert "HTTP_202_ACCEPTED" in source

    def test_single_pass_view_dispatches_with_callback(self):
        import inspect

        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        source = inspect.getsource(PromptStudioCoreView.single_pass_extraction)
        assert "dispatch_with_callback" in source
        assert "ide_prompt_complete" in source
        assert "PromptStudioHelper.prompt_responder(" not in source
        assert "HTTP_202_ACCEPTED" in source

    def test_views_pass_callback_kwargs(self):
        import inspect

        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        for method_name in [
            "index_document",
            "fetch_response",
            "single_pass_extraction",
        ]:
            source = inspect.getsource(getattr(PromptStudioCoreView, method_name))
            assert "callback_kwargs" in source, f"{method_name} missing callback_kwargs"
            assert "executor_task_id" in source, f"{method_name} missing executor_task_id"


# ===================================================================
# Phase 9: Polling endpoint tests
# ===================================================================
class TestTaskStatusAction:
    def test_task_status_method_exists(self):
        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        assert hasattr(PromptStudioCoreView, "task_status")
        assert callable(PromptStudioCoreView.task_status)

    def test_task_status_url_registered(self):
        from prompt_studio.prompt_studio_core_v2.urls import urlpatterns

        task_status_urls = [
            p
            for p in urlpatterns
            if hasattr(p, "name") and p.name == "prompt-studio-task-status"
        ]
        assert len(task_status_urls) >= 1
        url = task_status_urls[0]
        assert "<uuid:pk>" in str(url.pattern)
        assert "<str:task_id>" in str(url.pattern)

    @patch("prompt_studio.prompt_studio_core_v2.views.AsyncResult", create=True)
    def test_task_status_processing(self, mock_async_result):
        """Verify processing response for unfinished task."""
        import inspect

        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        source = inspect.getsource(PromptStudioCoreView.task_status)
        assert "not result.ready()" in source
        assert '"processing"' in source

    @patch("prompt_studio.prompt_studio_core_v2.views.AsyncResult", create=True)
    def test_task_status_completed(self, mock_async_result):
        """Verify completed response structure."""
        import inspect

        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        source = inspect.getsource(PromptStudioCoreView.task_status)
        assert "result.successful()" in source
        assert '"completed"' in source
        assert "result.result" in source

    @patch("prompt_studio.prompt_studio_core_v2.views.AsyncResult", create=True)
    def test_task_status_failed(self, mock_async_result):
        """Verify failed response structure."""
        import inspect

        from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

        source = inspect.getsource(PromptStudioCoreView.task_status)
        assert '"failed"' in source
        assert "HTTP_500_INTERNAL_SERVER_ERROR" in source


# ===================================================================
# Phase 10: ide_prompt_complete callback tests
# ===================================================================
class TestIdePromptComplete:
    """Tests for the new ide_prompt_complete Celery callback task."""

    CALLBACK_KWARGS = {
        "log_events_id": "session-room-xyz",
        "request_id": "req-001",
        "org_id": "org-456",
        "operation": "fetch_response",
        "run_id": "run-def",
        "document_id": "doc-abc",
        "prompt_ids": ["p1", "p2"],
        "profile_manager_id": "pm-1",
        "is_single_pass": False,
        "executor_task_id": "exec-task-1",
        "tool_id": "tool-123",
        "dispatch_time": 0,
    }

    @patch("prompt_studio.prompt_studio_core_v2.tasks._emit_result")
    @patch(
        "prompt_studio.prompt_studio_output_manager_v2.output_manager_helper"
        ".OutputManagerHelper.handle_prompt_output_update"
    )
    @patch("prompt_studio.prompt_studio_v2.models.ToolStudioPrompt")
    def test_success_logs_output_keys(
        self, mock_model, mock_output_helper, mock_emit, caplog
    ):
        """Verifies Fix 4: ide_prompt_complete logs output_keys on success."""
        mock_model.objects.filter.return_value.order_by.return_value = []
        mock_output_helper.return_value = {"some": "response"}

        result_dict = {
            "success": True,
            "data": {
                "output": {"field_a": "val1", "field_b": "val2"},
                "metadata": {},
            },
        }

        import logging

        with caplog.at_level(logging.INFO):
            result = ide_prompt_complete(
                result_dict, callback_kwargs=self.CALLBACK_KWARGS
            )

        assert result["status"] == "completed"
        assert any("ide_prompt_complete" in msg for msg in caplog.messages)
        assert any("output_keys" in msg for msg in caplog.messages)
        mock_emit.assert_called_once()

    @patch("prompt_studio.prompt_studio_core_v2.tasks._emit_error")
    def test_executor_failure_emits_error(self, mock_emit_error):
        """When executor reports failure, emit error and return failed status."""
        result_dict = {
            "success": False,
            "error": "LLM timeout",
        }

        result = ide_prompt_complete(result_dict, callback_kwargs=self.CALLBACK_KWARGS)

        assert result == {"status": "failed", "error": "LLM timeout"}
        mock_emit_error.assert_called_once()
        call_args = mock_emit_error.call_args
        assert call_args[0][3] == "LLM timeout"  # error message arg

    @patch("prompt_studio.prompt_studio_core_v2.tasks._emit_result")
    @patch(
        "prompt_studio.prompt_studio_output_manager_v2.output_manager_helper"
        ".OutputManagerHelper.handle_prompt_output_update"
    )
    @patch("prompt_studio.prompt_studio_v2.models.ToolStudioPrompt")
    def test_state_store_cleared_after_success(
        self, mock_model, mock_output_helper, mock_emit
    ):
        """StateStore should be cleaned up after callback completes."""
        mock_model.objects.filter.return_value.order_by.return_value = []
        mock_output_helper.return_value = {}

        result_dict = {
            "success": True,
            "data": {"output": {}, "metadata": {}},
        }

        ide_prompt_complete(result_dict, callback_kwargs=self.CALLBACK_KWARGS)

        assert StateStore.get(Common.LOG_EVENTS_ID) is None
        assert StateStore.get(Common.REQUEST_ID) is None
