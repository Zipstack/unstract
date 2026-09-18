"""IDE callbacks for a stopped prompt run (UN-1031).

A stopped run comes back as a SUCCESS carrying only the answers that finished,
so the callback has two jobs the completed path does not: persist just those
prompts, and tell the UI the run was stopped rather than that it failed or
completed. Getting either wrong is expensive — writing a blank over a good
answer, or leaving a spinner up forever.
"""

from unittest.mock import MagicMock, patch

import pytest

from unstract.core.prompt_run_cancellation import PROMPT_RUN_CANCELLED_ERROR

_PATCH_GET_CLIENT = "ide_callback.tasks._get_api_client"
_PATCH_EMIT_WS = "ide_callback.tasks._emit_websocket"
_PATCH_GET_PLUGIN = "client_plugin_registry.get_client_plugin"


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.post.return_value = {"success": True}
    api.update_prompt_output.return_value = {"success": True, "data": [{"id": "out1"}]}
    api.notify_hubspot.return_value = {"success": True}
    api.remove_document_indexing.return_value = {"success": True}
    return api


@pytest.fixture(autouse=True)
def no_client_plugins():
    with patch(_PATCH_GET_PLUGIN, return_value=None):
        yield


@pytest.fixture
def cb_kwargs():
    return {
        "log_events_id": "room-1",
        "org_id": "org-1",
        "operation": "fetch_response",
        "run_id": "run-1",
        "document_id": "doc-1",
        "prompt_ids": ["p1", "p2", "p3"],
        "profile_manager_id": "profile-1",
        "is_single_pass": False,
        "executor_task_id": "task-1",
        "tool_id": "tool-1",
        "dispatch_time": 0,
        "hubspot_user_id": 7,
    }


def _cancelled_result(output=None, cancelled_ids=("p2", "p3")):
    """What the executor returns when a stop lands mid-loop."""
    return {
        "success": True,
        "data": {"output": output or {"p1": "answer1"}, "metadata": {}},
        # NOTE: top-level metadata — the executor's own, not the per-prompt
        # persistence payload under data["metadata"].
        "metadata": {
            "usage_records": [],
            "cancelled": True,
            "cancelled_prompt_ids": list(cancelled_ids),
        },
    }


def _call_complete(result_dict, cb):
    from ide_callback.tasks import ide_prompt_complete

    return ide_prompt_complete(result_dict, cb)


@patch(_PATCH_EMIT_WS)
@patch(_PATCH_GET_CLIENT)
class TestStoppedRunPersistence:
    def test_persists_only_the_prompts_that_finished(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(_cancelled_result(), cb_kwargs)

        # p2/p3 have no answer; writing them would blank out whatever the
        # previous good run stored.
        assert mock_api.update_prompt_output.call_args.kwargs["prompt_ids"] == ["p1"]

    def test_skips_the_write_entirely_when_nothing_finished(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(
            _cancelled_result(output={}, cancelled_ids=("p1", "p2", "p3")), cb_kwargs
        )

        # The endpoint rejects an empty prompt_ids list, so there is nothing to
        # send — not an empty request.
        mock_api.update_prompt_output.assert_not_called()

    def test_tells_the_backend_the_run_was_stopped(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(_cancelled_result(), cb_kwargs)

        # The backend uses this to persist only prompts that actually have an
        # answer, so a stopped prompt cannot blank out a previous good one even
        # if the id list and the answers disagree.
        assert mock_api.update_prompt_output.call_args.kwargs["cancelled"] is True

    def test_completed_runs_are_not_flagged_as_stopped(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(
            {
                "success": True,
                "data": {"output": {"p1": "a"}, "metadata": {}},
                "metadata": {"usage_records": []},
            },
            cb_kwargs,
        )

        assert mock_api.update_prompt_output.call_args.kwargs["cancelled"] is False

    def test_does_not_report_a_stop_as_a_prompt_run(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(_cancelled_result(), cb_kwargs)

        # The analytics event means "the user ran a prompt", which this wasn't.
        mock_api.notify_hubspot.assert_not_called()


@patch(_PATCH_EMIT_WS)
@patch(_PATCH_GET_CLIENT)
class TestStoppedRunEvent:
    def test_emits_cancelled_not_completed(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        result = _call_complete(_cancelled_result(), cb_kwargs)

        data = mock_emit_ws.call_args[1]["data"]
        assert data["status"] == "cancelled"
        assert result["status"] == "cancelled"

    def test_names_every_prompt_so_no_spinner_is_left_running(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(_cancelled_result(), cb_kwargs)

        data = mock_emit_ws.call_args[1]["data"]
        # Persisted AND stopped prompts: the UI clears spinners from this list.
        assert set(data["prompt_ids"]) == {"p1", "p2", "p3"}
        assert data["cancelled_prompt_ids"] == ["p2", "p3"]

    def test_carries_the_run_id_so_the_ui_can_retire_the_run(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(_cancelled_result(), cb_kwargs)

        assert mock_emit_ws.call_args[1]["data"]["run_id"] == "run-1"

    def test_still_delivers_the_partial_results(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        _call_complete(_cancelled_result(), cb_kwargs)

        assert mock_emit_ws.call_args[1]["data"]["result"] == [{"id": "out1"}]


@patch(_PATCH_EMIT_WS)
@patch(_PATCH_GET_CLIENT)
class TestUncancelledRunUnaffected:
    def test_completed_run_behaves_as_before(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        result = _call_complete(
            {
                "success": True,
                "data": {"output": {"p1": "a"}, "metadata": {}},
                "metadata": {"usage_records": []},
            },
            cb_kwargs,
        )

        assert result["status"] == "completed"
        data = mock_emit_ws.call_args[1]["data"]
        assert data["status"] == "completed"
        assert data["cancelled_prompt_ids"] == []
        assert mock_api.update_prompt_output.call_args.kwargs["prompt_ids"] == [
            "p1",
            "p2",
            "p3",
        ]
        mock_api.notify_hubspot.assert_called_once()


@patch(_PATCH_EMIT_WS)
@patch(_PATCH_GET_CLIENT)
class TestErrorChannel:
    """A run stopped before it started arrives down the error channel."""

    def test_prompt_error_reports_a_stop_as_cancelled(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        from ide_callback.tasks import ide_prompt_error

        mock_get_client.return_value = mock_api
        ide_prompt_error("task-1", {**cb_kwargs, "error": PROMPT_RUN_CANCELLED_ERROR})

        data = mock_emit_ws.call_args[1]["data"]
        assert data["status"] == "cancelled"
        # No error text: the user caused this on purpose.
        assert data["error"] == ""
        assert data["cancelled_prompt_ids"] == ["p1", "p2", "p3"]

    def test_prompt_error_still_reports_real_failures(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        from ide_callback.tasks import ide_prompt_error

        mock_get_client.return_value = mock_api
        ide_prompt_error("task-1", {**cb_kwargs, "error": "LLM exploded"})

        data = mock_emit_ws.call_args[1]["data"]
        assert data["status"] == "failed"
        assert data["error"] == "LLM exploded"

    def test_index_error_clears_the_indexing_flag_on_a_stop(
        self, mock_get_client, mock_emit_ws, mock_api, cb_kwargs
    ):
        from ide_callback.tasks import ide_index_error

        mock_get_client.return_value = mock_api
        ide_index_error(
            "task-1",
            {
                **cb_kwargs,
                "error": PROMPT_RUN_CANCELLED_ERROR,
                "doc_id_key": "doc-key-1",
                "user_id": "user-1",
            },
        )

        # Left set, it blocks every prompt on this document for the flag's TTL.
        mock_api.remove_document_indexing.assert_called_once()
        assert mock_emit_ws.call_args[1]["data"]["status"] == "cancelled"
