"""Unit tests for IDE Callback Worker tasks.

Tests all 4 callback tasks (ide_index_complete, ide_index_error,
ide_prompt_complete, ide_prompt_error) by mocking the PromptStudioAPIClient
and verifying correct API calls, websocket emissions, return values,
and error handling.

Tasks are called as plain functions (bypassing Celery task machinery)
since we're testing callback logic, not Celery routing.
"""

import time
from unittest.mock import MagicMock, call, patch

import pytest

# Patch targets
_PATCH_GET_CLIENT = "ide_callback.tasks._get_api_client"
_PATCH_EMIT_WS = "ide_callback.tasks._emit_websocket"
_PATCH_ASYNC_RESULT = "celery.result.AsyncResult"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api():
    """Return a mocked PromptStudioAPIClient with default success responses."""
    api = MagicMock()
    api.post.return_value = {"success": True}
    api.get.return_value = {"success": True, "data": {}}
    api.mark_document_indexed.return_value = {"success": True}
    api.remove_document_indexing.return_value = {"success": True}
    api.update_index_manager.return_value = {"success": True}
    api.update_prompt_output.return_value = {"success": True, "data": [{"id": "out1"}]}
    api.notify_hubspot.return_value = {"success": True}
    api.get_summary_index_key.return_value = {
        "success": True,
        "data": {"doc_id": "summary-doc-id-hash"},
    }
    return api


@pytest.fixture
def base_index_kwargs():
    """Standard callback_kwargs for index tasks."""
    return {
        "log_events_id": "room-123",
        "org_id": "org-1",
        "user_id": "user-1",
        "document_id": "doc-1",
        "doc_id_key": "key-abc",
        "profile_manager_id": "profile-1",
        "executor_task_id": "task-1",
        "tool_id": "tool-1",
    }


@pytest.fixture
def base_prompt_kwargs():
    """Standard callback_kwargs for prompt tasks."""
    return {
        "log_events_id": "room-456",
        "org_id": "org-1",
        "operation": "fetch_response",
        "run_id": "run-1",
        "document_id": "doc-1",
        "prompt_ids": ["p1", "p2"],
        "profile_manager_id": "profile-1",
        "is_single_pass": False,
        "executor_task_id": "task-2",
        "tool_id": "tool-2",
        "dispatch_time": 0,
    }


@pytest.fixture
def success_result():
    """Standard executor success result dict."""
    return {
        "success": True,
        "data": {"doc_id": "computed-doc-id"},
    }


@pytest.fixture
def failure_result():
    """Standard executor failure result dict."""
    return {
        "success": False,
        "error": "Executor blew up",
    }


# ---------------------------------------------------------------------------
# TestIdeIndexComplete
# ---------------------------------------------------------------------------


class TestIdeIndexComplete:
    """Tests for ide_index_complete task."""

    def _call(self, result_dict, callback_kwargs=None):
        from ide_callback.tasks import ide_index_complete

        return ide_index_complete(result_dict, callback_kwargs)

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_success_path(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs, success_result):
        mock_get_client.return_value = mock_api

        result = self._call(success_result, base_index_kwargs)

        assert result["message"] == "Document indexed successfully."
        assert result["document_id"] == "doc-1"

        # mark_document_indexed called with correct args
        mock_api.mark_document_indexed.assert_called_once_with(
            org_id="org-1", user_id="user-1", doc_id_key="key-abc",
            doc_id="computed-doc-id", organization_id="org-1",
        )

        # update_index_manager called for primary profile
        mock_api.update_index_manager.assert_called_once_with(
            document_id="doc-1", profile_manager_id="profile-1",
            doc_id="computed-doc-id", organization_id="org-1",
        )

        # websocket emitted with success
        mock_emit_ws.assert_called_once()
        ws_call = mock_emit_ws.call_args
        assert ws_call[1]["room"] == "room-123"
        assert ws_call[1]["event"] == "prompt_studio_result"
        ws_data = ws_call[1]["data"]
        assert ws_data["status"] == "completed"
        assert ws_data["operation"] == "index_document"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_executor_failure(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs, failure_result):
        mock_get_client.return_value = mock_api

        result = self._call(failure_result, base_index_kwargs)

        assert result["status"] == "failed"
        assert result["error"] == "Executor blew up"

        # Should clean up indexing flag
        mock_api.remove_document_indexing.assert_called_once()

        # Should NOT mark as indexed
        mock_api.mark_document_indexed.assert_not_called()

        # Should emit error websocket
        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["status"] == "failed"
        assert ws_data["error"] == "Executor blew up"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_no_profile_manager(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs, success_result):
        """When profile_manager_id is None, skip update_index_manager."""
        mock_get_client.return_value = mock_api
        base_index_kwargs["profile_manager_id"] = None

        result = self._call(success_result, base_index_kwargs)

        assert result["document_id"] == "doc-1"
        mock_api.mark_document_indexed.assert_called_once()
        mock_api.update_index_manager.assert_not_called()

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_summary_indexing(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs, success_result):
        """Summary profile triggers get_summary_index_key + update_index_manager."""
        mock_get_client.return_value = mock_api
        base_index_kwargs["summary_profile_id"] = "summary-prof-1"
        base_index_kwargs["summarize_file_path"] = "/path/to/summary.txt"

        result = self._call(success_result, base_index_kwargs)

        assert result["document_id"] == "doc-1"

        # summary index key fetched via backend endpoint
        mock_api.get_summary_index_key.assert_called_once_with(
            summary_profile_id="summary-prof-1",
            summarize_file_path="/path/to/summary.txt",
            org_id="org-1",
            organization_id="org-1",
        )

        # update_index_manager called twice: primary + summary
        assert mock_api.update_index_manager.call_count == 2
        summary_call = mock_api.update_index_manager.call_args_list[1]
        assert summary_call == call(
            document_id="doc-1",
            profile_manager_id="summary-prof-1",
            doc_id="summary-doc-id-hash",
            is_summary=True,
            organization_id="org-1",
        )

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_summary_indexing_failure_non_fatal(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs, success_result):
        """Summary index failure doesn't prevent success return."""
        mock_get_client.return_value = mock_api
        base_index_kwargs["summary_profile_id"] = "summary-prof-1"
        base_index_kwargs["summarize_file_path"] = "/path/to/summary.txt"
        mock_api.get_summary_index_key.side_effect = Exception("backend down")

        result = self._call(success_result, base_index_kwargs)

        # Primary indexing still succeeds
        assert result["message"] == "Document indexed successfully."
        mock_api.mark_document_indexed.assert_called_once()

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_doc_id_falls_back_to_key(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs):
        """When result has no doc_id, falls back to doc_id_key."""
        mock_get_client.return_value = mock_api
        result_dict = {"success": True, "data": {}}

        result = self._call(result_dict, base_index_kwargs)

        assert result["document_id"] == "doc-1"
        mock_api.mark_document_indexed.assert_called_once_with(
            org_id="org-1", user_id="user-1", doc_id_key="key-abc",
            doc_id="key-abc", organization_id="org-1",
        )

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_exception_emits_error_and_reraises(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs, success_result):
        """Unexpected exception emits error websocket and re-raises."""
        mock_get_client.return_value = mock_api
        mock_api.mark_document_indexed.side_effect = RuntimeError("DB down")

        with pytest.raises(RuntimeError, match="DB down"):
            self._call(success_result, base_index_kwargs)

        mock_emit_ws.assert_called()
        last_ws = mock_emit_ws.call_args_list[-1]
        assert last_ws[1]["data"]["status"] == "failed"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_none_callback_kwargs(self, mock_get_client, mock_emit_ws, mock_api, success_result):
        """Passing None for callback_kwargs uses defaults without crashing."""
        mock_get_client.return_value = mock_api

        result = self._call(success_result, None)

        assert result["document_id"] == ""
        mock_api.mark_document_indexed.assert_called_once()


# ---------------------------------------------------------------------------
# TestIdeIndexError
# ---------------------------------------------------------------------------


class TestIdeIndexError:
    """Tests for ide_index_error task."""

    def _call(self, failed_task_id, callback_kwargs=None):
        from ide_callback.tasks import ide_index_error

        return ide_index_error(failed_task_id, callback_kwargs)

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_error_with_result(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs):
        """Retrieves error message from AsyncResult when available."""
        mock_get_client.return_value = mock_api

        mock_async_result = MagicMock()
        mock_async_result.result = ValueError("Index OOM")

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-id-1", base_index_kwargs)

        mock_api.remove_document_indexing.assert_called_once_with(
            org_id="org-1", user_id="user-1", doc_id_key="key-abc",
            organization_id="org-1",
        )

        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["status"] == "failed"
        assert "Index OOM" in ws_data["error"]

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_error_without_result(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs):
        """Falls back to default error message when AsyncResult has no result."""
        mock_get_client.return_value = mock_api

        mock_async_result = MagicMock()
        mock_async_result.result = None

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-id-2", base_index_kwargs)

        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["error"] == "Indexing failed"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_no_doc_id_key_skips_cleanup(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs):
        """When doc_id_key is empty, skip remove_document_indexing."""
        mock_get_client.return_value = mock_api
        base_index_kwargs["doc_id_key"] = ""

        mock_async_result = MagicMock()
        mock_async_result.result = None
        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-id-3", base_index_kwargs)

        mock_api.remove_document_indexing.assert_not_called()
        mock_emit_ws.assert_called_once()

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_exception_does_not_crash(self, mock_get_client, mock_emit_ws, mock_api, base_index_kwargs):
        """Exception in callback body is caught and logged, not re-raised."""
        mock_get_client.return_value = mock_api
        mock_api.remove_document_indexing.side_effect = RuntimeError("oops")

        mock_async_result = MagicMock()
        mock_async_result.result = None
        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            # Should not raise
            self._call("failed-task-id-4", base_index_kwargs)


# ---------------------------------------------------------------------------
# TestIdePromptComplete
# ---------------------------------------------------------------------------


class TestIdePromptComplete:
    """Tests for ide_prompt_complete task."""

    def _call(self, result_dict, callback_kwargs=None):
        from ide_callback.tasks import ide_prompt_complete

        return ide_prompt_complete(result_dict, callback_kwargs)

    def _make_result(self, output=None, metadata=None):
        return {
            "success": True,
            "data": {
                "output": output or {"p1": "answer1"},
                "metadata": metadata or {},
            },
        }

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_success_path(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        mock_get_client.return_value = mock_api

        result = self._call(self._make_result(), base_prompt_kwargs)

        assert result["status"] == "completed"
        assert result["operation"] == "fetch_response"

        mock_api.update_prompt_output.assert_called_once_with(
            run_id="run-1",
            prompt_ids=["p1", "p2"],
            outputs={"p1": "answer1"},
            document_id="doc-1",
            is_single_pass_extract=False,
            metadata={},
            profile_manager_id="profile-1",
            organization_id="org-1",
        )

        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["status"] == "completed"
        assert ws_data["operation"] == "fetch_response"
        assert ws_data["prompt_ids"] == ["p1", "p2"]

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_executor_failure(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs, failure_result):
        mock_get_client.return_value = mock_api

        result = self._call(failure_result, base_prompt_kwargs)

        assert result["status"] == "failed"
        mock_api.update_prompt_output.assert_not_called()

        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["status"] == "failed"
        assert ws_data["error"] == "Executor blew up"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_single_pass(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        mock_get_client.return_value = mock_api
        base_prompt_kwargs["is_single_pass"] = True

        self._call(self._make_result(), base_prompt_kwargs)

        call_kwargs = mock_api.update_prompt_output.call_args[1]
        assert call_kwargs["is_single_pass_extract"] is True

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_hubspot_event(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        mock_get_client.return_value = mock_api
        base_prompt_kwargs["hubspot_user_id"] = "hubspot-42"
        base_prompt_kwargs["is_first_prompt_run"] = True

        self._call(self._make_result(), base_prompt_kwargs)

        mock_api.notify_hubspot.assert_called_once_with(
            user_id="hubspot-42",
            event_name="PROMPT_RUN",
            is_first_for_org=True,
            action_label="prompt run",
            organization_id="org-1",
        )

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_hubspot_failure_non_fatal(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        """HubSpot notification failure doesn't prevent success."""
        mock_get_client.return_value = mock_api
        base_prompt_kwargs["hubspot_user_id"] = "hubspot-42"
        mock_api.notify_hubspot.side_effect = Exception("HubSpot down")

        result = self._call(self._make_result(), base_prompt_kwargs)

        assert result["status"] == "completed"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_elapsed_time_computed(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        """Elapsed time is computed from dispatch_time when provided."""
        mock_get_client.return_value = mock_api
        base_prompt_kwargs["dispatch_time"] = time.time() - 5

        self._call(self._make_result(), base_prompt_kwargs)

        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["elapsed"] >= 4  # Allow slight timing variance

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_exception_emits_error_and_reraises(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        mock_get_client.return_value = mock_api
        mock_api.update_prompt_output.side_effect = RuntimeError("Network")

        with pytest.raises(RuntimeError, match="Network"):
            self._call(self._make_result(), base_prompt_kwargs)

        # At least one error emission
        assert any(
            c[1].get("data", {}).get("status") == "failed"
            for c in mock_emit_ws.call_args_list
        )

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_output_api_failure_returns_empty_response(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        """When update_prompt_output returns success=False, response is []."""
        mock_get_client.return_value = mock_api
        mock_api.update_prompt_output.return_value = {"success": False}

        result = self._call(self._make_result(), base_prompt_kwargs)

        assert result["status"] == "completed"
        # The emitted result should be the empty list
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["result"] == []


# ---------------------------------------------------------------------------
# TestIdePromptError
# ---------------------------------------------------------------------------


class TestIdePromptError:
    """Tests for ide_prompt_error task."""

    def _call(self, failed_task_id, callback_kwargs=None):
        from ide_callback.tasks import ide_prompt_error

        return ide_prompt_error(failed_task_id, callback_kwargs)

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_error_with_result(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        mock_get_client.return_value = mock_api

        mock_async_result = MagicMock()
        mock_async_result.result = RuntimeError("LLM timeout")

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-99", base_prompt_kwargs)

        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["status"] == "failed"
        assert "LLM timeout" in ws_data["error"]
        assert ws_data["prompt_ids"] == ["p1", "p2"]
        assert ws_data["document_id"] == "doc-1"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_error_without_result(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        mock_get_client.return_value = mock_api

        mock_async_result = MagicMock()
        mock_async_result.result = None

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-100", base_prompt_kwargs)

        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["error"] == "Prompt execution failed"

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_minimal_callback_kwargs(self, mock_get_client, mock_emit_ws, mock_api):
        """Works with minimal/empty callback_kwargs."""
        mock_get_client.return_value = mock_api

        mock_async_result = MagicMock()
        mock_async_result.result = None

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-101", {})

        mock_emit_ws.assert_called_once()
        ws_data = mock_emit_ws.call_args[1]["data"]
        assert ws_data["operation"] == "fetch_response"
        assert ws_data["prompt_ids"] == []
        assert ws_data["document_id"] == ""

    @patch(_PATCH_EMIT_WS)
    @patch(_PATCH_GET_CLIENT)
    def test_exception_does_not_crash(self, mock_get_client, mock_emit_ws, mock_api, base_prompt_kwargs):
        """Exception in callback body is caught and logged, not re-raised."""
        mock_get_client.return_value = mock_api
        mock_emit_ws.side_effect = RuntimeError("ws broken")

        mock_async_result = MagicMock()
        mock_async_result.result = None

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            # Should not raise
            self._call("failed-task-102", base_prompt_kwargs)


# ---------------------------------------------------------------------------
# TestEmitWebSocket (integration of _emit_websocket helper)
# ---------------------------------------------------------------------------


class TestEmitWebSocket:
    """Test the _emit_websocket helper sends correct payload shape."""

    @patch(_PATCH_GET_CLIENT)
    def test_websocket_payload_not_double_wrapped(self, mock_get_client, mock_api):
        """Verify Fix 1: data is NOT double-wrapped in {"data": {"data": ...}}."""
        mock_get_client.return_value = mock_api

        from ide_callback.tasks import _emit_websocket

        test_data = {"task_id": "t1", "status": "completed"}
        _emit_websocket(mock_api, room="room-1", event="test_event", data=test_data)

        mock_api.post.assert_called_once()
        payload = mock_api.post.call_args[1]["data"]
        assert payload == {
            "room": "room-1",
            "event": "test_event",
            "data": {"task_id": "t1", "status": "completed"},
        }
        # The payload["data"] should be the raw data, NOT {"data": data}
        assert "data" not in payload["data"] or payload["data"] != {"data": test_data}

    @patch(_PATCH_GET_CLIENT)
    def test_websocket_post_failure_does_not_raise(self, mock_get_client, mock_api):
        """_emit_websocket catches exceptions and logs."""
        mock_get_client.return_value = mock_api
        mock_api.post.side_effect = RuntimeError("connection refused")

        from ide_callback.tasks import _emit_websocket

        # Should not raise
        _emit_websocket(mock_api, room="room-1", event="test_event", data={})


# ---------------------------------------------------------------------------
# TestJsonSafe
# ---------------------------------------------------------------------------


class TestJsonSafe:
    """Test _json_safe serialization of non-standard types."""

    def test_uuid_serialized(self):
        import uuid

        from ide_callback.tasks import _json_safe

        val = {"id": uuid.UUID("12345678-1234-5678-1234-567812345678")}
        result = _json_safe(val)
        assert result["id"] == "12345678-1234-5678-1234-567812345678"
        assert isinstance(result["id"], str)

    def test_datetime_serialized(self):
        from datetime import datetime

        from ide_callback.tasks import _json_safe

        val = {"ts": datetime(2024, 1, 15, 12, 0, 0)}
        result = _json_safe(val)
        assert isinstance(result["ts"], str)
        assert "2024-01-15" in result["ts"]

    def test_nested_types(self):
        import uuid
        from datetime import date

        from ide_callback.tasks import _json_safe

        val = {
            "items": [
                {"id": uuid.uuid4(), "date": date(2024, 6, 1)},
            ]
        }
        result = _json_safe(val)
        assert isinstance(result["items"][0]["id"], str)
        assert isinstance(result["items"][0]["date"], str)
