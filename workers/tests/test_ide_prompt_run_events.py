"""Additive fields on the ``prompt_studio_result`` events of a prompt run.

The completed event carries the persisted output rows (``outputs``) and the
failed event carries ``error_details``. Both carry ``run_id``. The existing
fields keep their meaning: ``result`` stays absent on a completed prompt run,
so the v0 frontend keeps refetching ``prompt-output/``.
"""

from unittest.mock import MagicMock, patch

import pytest

_PATCH_GET_CLIENT = "ide_callback.tasks._get_api_client"
_PATCH_EMIT_WS = "ide_callback.tasks._emit_websocket"
_PATCH_ASYNC_RESULT = "celery.result.AsyncResult"

_NULL_DETAILS = {"provider": None, "request_id": None, "retry_after_seconds": None}
_ROWS = [{"prompt_output_id": "out-1", "prompt_id": "p1", "output": "answer"}]


@pytest.fixture
def api():
    client = MagicMock()
    client.update_prompt_output.return_value = {"success": True, "data": _ROWS}
    return client


@pytest.fixture
def cb():
    return {
        "log_events_id": "room-1",
        "org_id": "org-1",
        "operation": "fetch_response",
        "run_id": "run-1",
        "document_id": "doc-1",
        "prompt_ids": ["p1"],
        "profile_manager_id": "profile-1",
        "is_single_pass": False,
        "executor_task_id": "task-1",
        "tool_id": "tool-1",
        "dispatch_time": 0,
    }


@pytest.fixture(autouse=True)
def _no_plugins():
    with patch("client_plugin_registry.get_client_plugin", return_value=None):
        yield


def _success():
    return {"success": True, "data": {"output": {"p1": "answer"}, "metadata": {}}}


def _complete(api, cb, result_dict):
    from ide_callback.tasks import ide_prompt_complete

    with patch(_PATCH_GET_CLIENT, return_value=api), patch(_PATCH_EMIT_WS) as emit:
        ide_prompt_complete(result_dict, cb)
    emit.assert_called_once()
    return emit.call_args[1]["data"]


class TestCompletedEvent:
    def test_carries_the_persisted_rows(self, api, cb):
        event = _complete(api, cb, _success())

        assert event["outputs"] == _ROWS
        assert event["run_id"] == "run-1"

    def test_result_stays_absent_for_v0(self, api, cb):
        event = _complete(api, cb, _success())

        assert "result" not in event
        assert event["status"] == "completed"
        assert event["task_id"] == "task-1"

    @pytest.mark.parametrize(
        "response",
        [
            {"success": False, "data": _ROWS},
            {"success": True},
            {"success": True, "data": {"not": "a list"}},
            None,
        ],
    )
    def test_outputs_null_when_rows_unavailable(self, api, cb, response):
        api.update_prompt_output.return_value = response

        event = _complete(api, cb, _success())

        assert event["outputs"] is None
        assert event["status"] == "completed"

    def test_outputs_null_when_over_the_size_cap(self, api, cb):
        with patch("ide_callback.run_event_fields.MAX_INLINE_OUTPUTS_BYTES", 10):
            event = _complete(api, cb, _success())

        assert event["outputs"] is None

    def test_outputs_kept_at_the_size_cap(self, api, cb):
        import json

        size = len(json.dumps(_ROWS).encode("utf-8"))
        with patch("ide_callback.run_event_fields.MAX_INLINE_OUTPUTS_BYTES", size):
            event = _complete(api, cb, _success())

        assert event["outputs"] == _ROWS


class TestFailedEventFromExecutorResult:
    def _failure(self, metadata):
        return {"success": False, "error": "Error from openai. 429", "metadata": metadata}

    def test_error_details_copied_from_executor_metadata(self, api, cb):
        details = {"provider": "azure", "request_id": "req-9", "retry_after_seconds": 60}

        event = _complete(api, cb, self._failure({"error_details": details}))

        assert event["error_details"] == details
        assert event["error"] == "Error from openai. 429"
        assert event["status"] == "failed"
        assert event["run_id"] == "run-1"

    @pytest.mark.parametrize("metadata", [{}, None, {"error_details": "nope"}])
    def test_error_details_null_fields_when_absent(self, api, cb, metadata):
        event = _complete(api, cb, self._failure(metadata))

        assert event["error_details"] == _NULL_DETAILS

    def test_unknown_keys_and_bad_types_dropped(self, api, cb):
        details = {
            "provider": 42,
            "request_id": "req-1",
            "retry_after_seconds": "60",
            "api_key": "sk-secret",
        }

        event = _complete(api, cb, self._failure({"error_details": details}))

        assert event["error_details"] == {
            "provider": None,
            "request_id": "req-1",
            "retry_after_seconds": None,
        }

    def test_boolean_is_not_a_retry_hint(self, api, cb):
        details = {"retry_after_seconds": True}

        event = _complete(api, cb, self._failure({"error_details": details}))

        assert event["error_details"]["retry_after_seconds"] is None


class TestFailedEventFromCallbackException:
    def test_null_details_and_run_id(self, api, cb):
        from ide_callback.tasks import ide_prompt_complete

        api.update_prompt_output.side_effect = RuntimeError("boom")
        with patch(_PATCH_GET_CLIENT, return_value=api), patch(_PATCH_EMIT_WS) as emit:
            with pytest.raises(RuntimeError):
                ide_prompt_complete(_success(), cb)

        event = emit.call_args[1]["data"]
        assert event["status"] == "failed"
        assert event["error"] == "boom"
        assert event["error_details"] == _NULL_DETAILS
        assert event["run_id"] == "run-1"


class TestFailedEventFromErrorCallback:
    def test_null_details_and_run_id(self, api, cb):
        from ide_callback.tasks import ide_prompt_error

        async_result = MagicMock(result=RuntimeError("LLM timeout"))
        with (
            patch(_PATCH_GET_CLIENT, return_value=api),
            patch(_PATCH_EMIT_WS) as emit,
            patch(_PATCH_ASYNC_RESULT, return_value=async_result),
        ):
            ide_prompt_error("failed-1", cb)

        event = emit.call_args[1]["data"]
        assert event["error"] == "LLM timeout"
        assert event["error_details"] == _NULL_DETAILS
        assert event["run_id"] == "run-1"
