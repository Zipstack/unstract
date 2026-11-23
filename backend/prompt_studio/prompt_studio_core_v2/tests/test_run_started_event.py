"""The ``prompt_studio_run_started`` socket event.

Each prompt run endpoint sends it once the executor task is dispatched. It is a
separate event name, so the v0 ``prompt_studio_result`` listener never sees it.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from prompt_studio.prompt_studio_core_v2 import run_events
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView

_EMIT = "prompt_studio.prompt_studio_core_v2.run_events._emit_websocket_event"
_DISPATCH_TIME = 1795000000.5  # 2026-11-18T11:06:40.500000+00:00


def _cb_kwargs(**overrides):
    cb = {
        "log_events_id": "room-1",
        "operation": "fetch_response",
        "run_id": "run-1",
        "document_id": "doc-1",
        "tool_id": "tool-1",
        "prompt_ids": ["p1", "p2"],
        "profile_manager_id": "profile-1",
        "executor_task_id": "task-1",
        "dispatch_time": _DISPATCH_TIME,
    }
    cb.update(overrides)
    return cb


class TestEmitRunStarted:
    def test_payload(self):
        with patch(_EMIT) as emit:
            run_events.emit_run_started(_cb_kwargs())

        emit.assert_called_once_with(
            "room-1",
            "prompt_studio_run_started",
            {
                "task_id": "task-1",
                "operation": "fetch_response",
                "tool_id": "tool-1",
                "status": "started",
                "run_id": "run-1",
                "prompt_ids": ["p1", "p2"],
                "document_id": "doc-1",
                "profile_manager_id": "profile-1",
                "started_at": "2026-11-18T11:06:40.500000+00:00",
            },
        )

    def test_not_the_v0_result_event(self):
        assert run_events.PROMPT_STUDIO_RUN_STARTED_EVENT != "prompt_studio_result"

    @pytest.mark.parametrize("room", ["", None])
    def test_skipped_without_a_room(self, room):
        with patch(_EMIT) as emit:
            run_events.emit_run_started(_cb_kwargs(log_events_id=room))

        emit.assert_not_called()

    def test_started_at_null_without_dispatch_time(self):
        with patch(_EMIT) as emit:
            run_events.emit_run_started(_cb_kwargs(dispatch_time=None))

        assert emit.call_args[0][2]["started_at"] is None

    def test_ids_made_json_safe(self):
        import uuid

        tool_id = uuid.uuid4()
        with patch(_EMIT) as emit:
            run_events.emit_run_started(_cb_kwargs(tool_id=tool_id))

        assert emit.call_args[0][2]["tool_id"] == str(tool_id)

    def test_emit_failure_does_not_raise(self):
        with patch(_EMIT, side_effect=RuntimeError("redis down")):
            run_events.emit_run_started(_cb_kwargs())


# --- Wiring: every dispatching endpoint sends the event after dispatch -------

_VIEWS = "prompt_studio.prompt_studio_core_v2.views"


def _view():
    view = PromptStudioCoreView()
    tool = MagicMock(tool_id="tool-1")
    view.get_object = MagicMock(return_value=tool)
    return view


def _request(**data):
    return SimpleNamespace(data=data, user=MagicMock(pk=7))


@pytest.fixture
def wiring():
    """Patch every collaborator of the run endpoints; yield the call record."""
    calls = []
    dispatcher = MagicMock()
    dispatcher.dispatch_with_callback.side_effect = lambda *a, **k: (
        calls.append("dispatch") or MagicMock(id=k["task_id"])
    )
    cb = _cb_kwargs()

    def _emit(cb_kwargs):
        calls.append(("started", cb_kwargs))

    prompt = MagicMock(
        enforce_type="text", prompt_type="PROMPT", active=True, prompt_id="p1"
    )
    document = MagicMock(document_name="doc.pdf")
    patches = [
        patch(f"{_VIEWS}._multi_var_lookup_block_response", return_value=None),
        patch(f"{_VIEWS}.UserSessionUtils.get_organization_id", return_value="org-1"),
        patch(f"{_VIEWS}.ToolStudioPrompt.objects"),
        patch(f"{_VIEWS}.DocumentManager.objects"),
        patch(f"{_VIEWS}.CustomTool.objects"),
        patch(
            "prompt_studio.prompt_studio_output_manager_v2.models."
            "PromptStudioOutputManager.objects"
        ),
        patch(
            f"{_VIEWS}.PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory",
            return_value="/tmp",
        ),
        patch(f"{_VIEWS}.PromptStudioHelper._get_dispatcher", return_value=dispatcher),
        patch(f"{_VIEWS}.emit_run_started", side_effect=_emit),
    ]
    for builder in (
        "build_fetch_response_payload",
        "build_bulk_fetch_response_payload",
        "build_single_pass_payload",
    ):
        patches.append(
            patch(f"{_VIEWS}.PromptStudioHelper.{builder}", return_value=(object(), cb))
        )
    started = [p.start() for p in patches]
    try:
        prompts_manager, documents_manager = started[2], started[3]
        prompts_manager.get.return_value = prompt
        prompts_manager.filter.return_value.order_by.return_value = [prompt]
        documents_manager.get.return_value = document
        yield calls, cb
    finally:
        for p in patches:
            p.stop()


def _assert_started_after_dispatch(calls, cb):
    assert calls[0] == "dispatch"
    assert calls[1] == ("started", cb)
    assert cb["executor_task_id"]
    assert cb["dispatch_time"]


class TestEndpointsSendStarted:
    def test_fetch_response(self, wiring):
        calls, cb = wiring

        response = _view().fetch_response(
            _request(id="p1", document_id="doc-1", run_id="run-1")
        )

        assert response.status_code == 202
        _assert_started_after_dispatch(calls, cb)

    def test_bulk_fetch_response(self, wiring):
        calls, cb = wiring

        response = _view().bulk_fetch_response(
            _request(prompt_ids=["p1"], document_id="doc-1", run_id="run-1")
        )

        assert response.status_code == 202
        _assert_started_after_dispatch(calls, cb)

    def test_single_pass_extraction(self, wiring):
        calls, cb = wiring

        response = _view().single_pass_extraction(
            _request(document_id="doc-1", run_id="run-1"), pk="tool-1"
        )

        assert response.status_code == 202
        _assert_started_after_dispatch(calls, cb)

    def test_agentic_table(self, wiring):
        calls, cb = wiring
        modifier = MagicMock()
        modifier.return_value.build_agentic_table_payload.return_value = (object(), cb)
        agentic = MagicMock(enforce_type="agentic_table")

        with (
            patch(f"{_VIEWS}.get_plugin", return_value={"service_class": modifier}),
            patch(f"{_VIEWS}.ToolStudioPrompt.objects") as prompts_manager,
        ):
            prompts_manager.get.return_value = agentic
            response = _view().fetch_response(
                _request(id="p1", document_id="doc-1", run_id="run-1")
            )

        assert response.status_code == 202
        _assert_started_after_dispatch(calls, cb)

    def test_pending_index_sends_nothing(self, wiring):
        calls, _ = wiring
        with patch(
            f"{_VIEWS}.PromptStudioHelper.build_fetch_response_payload",
            return_value=(None, {"status": "pending"}),
        ):
            response = _view().fetch_response(
                _request(id="p1", document_id="doc-1", run_id="run-1")
            )

        assert response.status_code == 202
        assert calls == []
