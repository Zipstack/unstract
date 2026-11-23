"""Index failures are recorded for the Documents tab, and recording never
changes what the callbacks already do.
"""

from unittest.mock import MagicMock, patch

import pytest

_PATCH_GET_CLIENT = "ide_callback.tasks._get_api_client"
_PATCH_EMIT_WS = "ide_callback.tasks._emit_websocket"
_PATCH_ASYNC_RESULT = "celery.result.AsyncResult"

_KWARGS = {
    "log_events_id": "room-123",
    "org_id": "org-1",
    "user_id": "user-1",
    "document_id": "doc-1",
    "doc_id_key": "key-abc",
    "profile_manager_id": "profile-1",
    "executor_task_id": "task-1",
    "tool_id": "tool-1",
}


def _recorded(api: MagicMock, error: str) -> None:
    # user_id + doc_id_key name the attempt's indexing-cache key, which the
    # backend reads to drop a write that a newer success has overtaken.
    api.mark_index_failed.assert_called_once_with(
        document_id="doc-1",
        profile_manager_id="profile-1",
        error=error,
        organization_id="org-1",
        user_id="user-1",
        doc_id_key="key-abc",
    )


@pytest.fixture
def api():
    with patch(_PATCH_GET_CLIENT) as get_client, patch(_PATCH_EMIT_WS) as emit:
        client = MagicMock()
        get_client.return_value = client
        client.emit = emit
        yield client


def _index_error(kwargs: dict) -> None:
    from ide_callback.tasks import ide_index_error

    result = MagicMock()
    result.result = ValueError("Index OOM")
    with patch(_PATCH_ASYNC_RESULT, return_value=result):
        ide_index_error("failed-task", kwargs)


class TestRecordsTheFailure:
    def test_executor_failure(self, api):
        from ide_callback.tasks import ide_index_complete

        ide_index_complete({"success": False, "error": "Executor blew up"}, dict(_KWARGS))

        _recorded(api, "Executor blew up")

    def test_bookkeeping_exception(self, api):
        from ide_callback.tasks import ide_index_complete

        api.mark_document_indexed.side_effect = RuntimeError("DB down")
        with pytest.raises(RuntimeError):
            ide_index_complete({"success": True, "data": {"doc_id": "d"}}, dict(_KWARGS))

        _recorded(api, "DB down")

    def test_link_error_callback(self, api):
        _index_error(dict(_KWARGS))

        api.mark_index_failed.assert_called_once()
        kwargs = api.mark_index_failed.call_args.kwargs
        assert "Index OOM" in kwargs["error"]
        assert (kwargs["user_id"], kwargs["doc_id_key"]) == ("user-1", "key-abc")

    def test_success_records_nothing(self, api):
        from ide_callback.tasks import ide_index_complete

        ide_index_complete({"success": True, "data": {"doc_id": "d"}}, dict(_KWARGS))

        api.mark_index_failed.assert_not_called()


class TestRecordingIsBestEffort:
    def test_no_profile_skips_the_call(self, api):
        _index_error({**_KWARGS, "profile_manager_id": None})

        api.mark_index_failed.assert_not_called()

    def test_a_failed_record_still_cleans_up_and_emits(self, api):
        from ide_callback.tasks import ide_index_complete

        api.mark_index_failed.side_effect = RuntimeError("backend down")

        result = ide_index_complete(
            {"success": False, "error": "Executor blew up"}, dict(_KWARGS)
        )

        assert result == {"status": "failed", "error": "Executor blew up"}
        api.remove_document_indexing.assert_called_once()
        api.emit.assert_called_once()
        assert api.emit.call_args.kwargs["data"]["status"] == "failed"

    def test_link_error_still_emits_when_recording_fails(self, api):
        api.mark_index_failed.side_effect = RuntimeError("backend down")

        _index_error(dict(_KWARGS))

        api.remove_document_indexing.assert_called_once()
        api.emit.assert_called_once()


class TestRecordingWaitsForTheUser:
    """The best-effort write is retried on 5xx, so it goes last."""

    def _order(self, api) -> list[str]:
        order: list[str] = []
        api.remove_document_indexing.side_effect = lambda **_: order.append("cleanup")
        api.emit.side_effect = lambda *a, **k: order.append("emit")
        api.mark_index_failed.side_effect = lambda **_: order.append("record")
        return order

    def test_executor_failure_records_after_cleanup_and_event(self, api):
        from ide_callback.tasks import ide_index_complete

        order = self._order(api)
        ide_index_complete({"success": False, "error": "Executor blew up"}, dict(_KWARGS))

        assert order == ["cleanup", "emit", "record"]

    def test_link_error_records_after_cleanup_and_event(self, api):
        order = self._order(api)
        _index_error(dict(_KWARGS))

        assert order == ["cleanup", "emit", "record"]

    def test_link_error_still_records_when_cleanup_fails(self, api):
        api.remove_document_indexing.side_effect = RuntimeError("redis down")

        _index_error(dict(_KWARGS))

        api.mark_index_failed.assert_called_once()


class TestRecordsTheRightReason:
    def test_a_cleanup_error_keeps_the_executor_reason(self, api):
        from ide_callback.tasks import ide_index_complete

        api.remove_document_indexing.side_effect = RuntimeError("redis down")
        with pytest.raises(RuntimeError):
            ide_index_complete(
                {"success": False, "error": "Executor blew up"}, dict(_KWARGS)
            )

        _recorded(api, "Executor blew up")

    def test_an_error_after_indexing_records_nothing(self, api):
        from ide_callback.tasks import ide_index_complete

        # The "completed" event fails after the index is written.
        api.emit.side_effect = [RuntimeError("socket down"), None]
        with pytest.raises(RuntimeError):
            ide_index_complete({"success": True, "data": {"doc_id": "d"}}, dict(_KWARGS))

        api.mark_index_failed.assert_not_called()

    def test_an_empty_reason_is_recorded_as_unknown(self, api):
        from ide_callback.tasks import _UNKNOWN_EXECUTOR_ERROR, ide_index_complete

        ide_index_complete({"success": False, "error": None}, dict(_KWARGS))

        _recorded(api, _UNKNOWN_EXECUTOR_ERROR)

    def test_a_soft_time_limit_is_not_swallowed(self, api):
        from celery.exceptions import SoftTimeLimitExceeded
        from ide_callback.tasks import _record_index_failure

        api.mark_index_failed.side_effect = SoftTimeLimitExceeded()
        with pytest.raises(SoftTimeLimitExceeded):
            _record_index_failure(
                api, "doc-1", "profile-1", "boom", "org-1", "user-1", "key-abc"
            )


def test_client_posts_to_the_backend_route():
    from shared.clients.prompt_studio_client import PromptStudioAPIClient

    client = PromptStudioAPIClient.__new__(PromptStudioAPIClient)
    with patch.object(PromptStudioAPIClient, "post") as post:
        client.mark_index_failed(
            document_id="doc-1",
            profile_manager_id="profile-1",
            error="boom",
            organization_id="org-1",
            user_id="user-1",
            doc_id_key="key-abc",
        )

    # The backend route is pinned by its own test against this path.
    post.assert_called_once_with(
        "v1/prompt-studio/index-error/",
        data={
            "document_id": "doc-1",
            "profile_manager_id": "profile-1",
            "error": "boom",
            "org_id": "org-1",
            "user_id": "user-1",
            "doc_id_key": "key-abc",
        },
        organization_id="org-1",
    )
