"""Unit tests for Agent-KV terminal callback tasks (spec §5.3).

Mirrors ``tests/test_ide_callback.py``'s style: task functions are called
directly (bypassing Celery task machinery) since we're testing callback
logic, not Celery routing. ``_get_api_client`` and ``send_webhook`` are
mocked at the ``ide_callback.agent_kv_tasks`` import site.
"""

from unittest.mock import MagicMock, patch

import pytest

_PATCH_GET_CLIENT = "ide_callback.agent_kv_tasks._get_api_client"
_PATCH_SEND_WEBHOOK = "ide_callback.agent_kv_tasks.send_webhook"
_PATCH_ASYNC_RESULT = "celery.result.AsyncResult"

_UNKNOWN = "Executor failed without an error message"


@pytest.fixture
def mock_api():
    """A mocked InternalAPIClient whose agent_kv_finalize succeeds with a webhook."""
    api = MagicMock()
    api.agent_kv_finalize.return_value = {
        "finalized": True,
        "webhook_url": "https://example.com/hook",
        "status": "completed",
    }
    return api


@pytest.fixture
def cb_kwargs():
    """Standard callback_kwargs, matching agent_kv.dispatch.dispatch_job's shape."""
    return {"job_id": "job-1", "org_id": "org-1"}


# ---------------------------------------------------------------------------
# agent_kv_complete
# ---------------------------------------------------------------------------


class TestAgentKvComplete:
    def _call(self, result_dict, callback_kwargs=None):
        from ide_callback.agent_kv_tasks import agent_kv_complete

        return agent_kv_complete(result_dict, callback_kwargs)

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_success_path_finalizes_true_with_engine_result(
        self, mock_get_client, mock_send_webhook, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api
        result_dict = {
            "success": True,
            "data": {
                "output": {"field_1": "value_1"},
                "usage_summary": {"total_tokens": 42},
            },
            "error": None,
        }

        result = self._call(result_dict, cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1",
            "org-1",
            success=True,
            result={"field_1": "value_1"},
            usage_summary={"total_tokens": 42},
        )
        assert result == {"job_id": "job-1", "finalized": True}

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_missing_output_and_usage_summary_default_to_empty(
        self, mock_get_client, mock_send_webhook, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api
        result_dict = {"success": True, "data": {}, "error": None}

        self._call(result_dict, cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=True, result={}, usage_summary=None
        )

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_executor_reported_failure_finalizes_false_with_error(
        self, mock_get_client, mock_send_webhook, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api
        result_dict = {"success": False, "data": None, "error": "boom"}

        self._call(result_dict, cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=False, error="boom"
        )

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_executor_failure_with_no_error_message_uses_fallback(
        self, mock_get_client, mock_send_webhook, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api
        result_dict = {"success": False, "data": None, "error": None}

        self._call(result_dict, cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=False, error=_UNKNOWN
        )

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_none_callback_kwargs_uses_empty_defaults(
        self, mock_get_client, mock_send_webhook, mock_api
    ):
        mock_get_client.return_value = mock_api
        result_dict = {"success": True, "data": {"output": {}}, "error": None}

        result = self._call(result_dict, None)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "", "", success=True, result={}, usage_summary=None
        )
        assert result["job_id"] == ""

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_returns_finalized_false_when_finalize_says_so(
        self, mock_get_client, mock_send_webhook, cb_kwargs
    ):
        """A duplicate/late callback: the backend reports finalized=False."""
        api = MagicMock()
        api.agent_kv_finalize.return_value = {
            "finalized": False,
            "webhook_url": "",
            "status": "completed",
        }
        mock_get_client.return_value = api
        result_dict = {"success": True, "data": {"output": {}}, "error": None}

        result = self._call(result_dict, cb_kwargs)

        assert result == {"job_id": "job-1", "finalized": False}

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_finalize_raising_is_logged_and_reraised(
        self, mock_get_client, mock_send_webhook, cb_kwargs, caplog
    ):
        """agent_kv_complete mirrors ide_index_complete: log, then re-raise."""
        import logging

        api = MagicMock()
        api.agent_kv_finalize.side_effect = RuntimeError("backend unreachable")
        mock_get_client.return_value = api
        result_dict = {"success": True, "data": {"output": {}}, "error": None}

        with caplog.at_level(logging.ERROR, logger="ide_callback.agent_kv_tasks"):
            with pytest.raises(RuntimeError, match="backend unreachable"):
                self._call(result_dict, cb_kwargs)

        assert "agent_kv_complete callback failed" in caplog.text
        mock_send_webhook.assert_not_called()


# ---------------------------------------------------------------------------
# agent_kv_error
# ---------------------------------------------------------------------------


class TestAgentKvError:
    def _call(self, failed_task_id, callback_kwargs=None):
        from ide_callback.agent_kv_tasks import agent_kv_error

        return agent_kv_error(failed_task_id, callback_kwargs)

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_error_link_finalizes_false_with_result_backend_error(
        self, mock_get_client, mock_send_webhook, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api
        mock_async_result = MagicMock()
        mock_async_result.result = RuntimeError("executor crashed")

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            result = self._call("failed-task-1", cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=False, error="executor crashed"
        )
        assert result == {"job_id": "job-1", "finalized": True}

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_error_link_falls_back_when_no_result_available(
        self, mock_get_client, mock_send_webhook, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api
        mock_async_result = MagicMock()
        mock_async_result.result = None

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-2", cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=False, error=_UNKNOWN
        )

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_error_link_falls_back_when_lookup_raises(
        self, mock_get_client, mock_send_webhook, mock_api, cb_kwargs
    ):
        mock_get_client.return_value = mock_api

        with patch(_PATCH_ASYNC_RESULT, side_effect=RuntimeError("backend down")):
            self._call("failed-task-3", cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=False, error=_UNKNOWN
        )

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_none_callback_kwargs_uses_empty_defaults(
        self, mock_get_client, mock_send_webhook, mock_api
    ):
        mock_get_client.return_value = mock_api

        with patch(_PATCH_ASYNC_RESULT, return_value=MagicMock(result=None)):
            result = self._call("failed-task-4", None)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "", "", success=False, error=_UNKNOWN
        )
        assert result["job_id"] == ""

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_pg_transport_explicit_error_preferred_over_async_result(
        self, mock_get_client, mock_send_webhook, mock_api
    ):
        """PG-queue self-chained path: callback_kwargs carries the real error.

        ``queue_backend/pg_queue/consumer.py``'s ``_chain_continuation`` injects
        the executor's real error into ``callback_kwargs["error"]`` because the
        PG path runs the executor eagerly and never writes a Celery result
        backend entry under ``failed_task_id`` -- so this must be preferred
        over (and must skip) the ``AsyncResult`` lookup entirely.
        """
        mock_get_client.return_value = mock_api
        pg_cb_kwargs = {"job_id": "job-1", "org_id": "org-1", "error": "real cause"}

        with patch(_PATCH_ASYNC_RESULT) as mock_async_result_cls:
            result = self._call("failed-task-pg-1", pg_cb_kwargs)

        mock_async_result_cls.assert_not_called()
        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=False, error="real cause"
        )
        assert result == {"job_id": "job-1", "finalized": True}

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_pg_transport_empty_explicit_error_falls_back_to_async_result(
        self, mock_get_client, mock_send_webhook, mock_api
    ):
        """An empty-string explicit error must not be persisted verbatim --
        it's falsy, so it falls through to the result-backend lookup (then
        ``_UNKNOWN``), same as an absent explicit error.
        """
        mock_get_client.return_value = mock_api
        pg_cb_kwargs = {"job_id": "job-1", "org_id": "org-1", "error": ""}
        mock_async_result = MagicMock()
        mock_async_result.result = RuntimeError("real backend cause")

        with patch(_PATCH_ASYNC_RESULT, return_value=mock_async_result):
            self._call("failed-task-empty-error", pg_cb_kwargs)

        mock_api.agent_kv_finalize.assert_called_once_with(
            "job-1", "org-1", success=False, error="real backend cause"
        )

    @patch(_PATCH_SEND_WEBHOOK)
    @patch(_PATCH_GET_CLIENT)
    def test_finalize_raising_is_swallowed_and_logged(
        self, mock_get_client, mock_send_webhook, cb_kwargs, caplog
    ):
        """agent_kv_error mirrors ide_index_error: swallow, log, don't raise."""
        import logging

        api = MagicMock()
        api.agent_kv_finalize.side_effect = RuntimeError("backend unreachable")
        mock_get_client.return_value = api

        with (
            patch(_PATCH_ASYNC_RESULT, return_value=MagicMock(result=None)),
            caplog.at_level(logging.ERROR, logger="ide_callback.agent_kv_tasks"),
        ):
            result = self._call("failed-task-6", cb_kwargs)

        assert result is None
        assert "agent_kv_error callback failed" in caplog.text
        mock_send_webhook.assert_not_called()


# ---------------------------------------------------------------------------
# Webhook firing rules (shared by both callbacks)
# ---------------------------------------------------------------------------


class TestWebhookFiring:
    """Webhook fires iff finalize returns finalized=True AND a non-empty webhook_url."""

    def _call_complete(self, callback_kwargs, api):
        from ide_callback.agent_kv_tasks import agent_kv_complete

        with patch(_PATCH_GET_CLIENT, return_value=api):
            result_dict = {"success": True, "data": {"output": {"x": 1}}, "error": None}
            return agent_kv_complete(result_dict, callback_kwargs)

    @patch(_PATCH_SEND_WEBHOOK)
    def test_webhook_fires_when_finalized_true_and_url_present(
        self, mock_send_webhook, cb_kwargs
    ):
        api = MagicMock()
        api.agent_kv_finalize.return_value = {
            "finalized": True,
            "webhook_url": "https://example.com/hook",
            "status": "completed",
        }

        self._call_complete(cb_kwargs, api)

        mock_send_webhook.assert_called_once_with(
            "https://example.com/hook",
            {"job_id": "job-1", "status": "completed"},
            allow_insecure=False,
        )

    @patch(_PATCH_SEND_WEBHOOK)
    def test_webhook_not_fired_on_duplicate_finalize_false(
        self, mock_send_webhook, cb_kwargs
    ):
        """Duplicate/late finalize: finalized=False must not re-fire the webhook,
        even though the job (from an earlier finalize) still carries a webhook_url.
        """
        api = MagicMock()
        api.agent_kv_finalize.return_value = {
            "finalized": False,
            "webhook_url": "https://example.com/hook",
            "status": "completed",
        }

        self._call_complete(cb_kwargs, api)

        mock_send_webhook.assert_not_called()

    @patch(_PATCH_SEND_WEBHOOK)
    def test_webhook_not_fired_when_url_empty(self, mock_send_webhook, cb_kwargs):
        """finalized=True but the job has no webhook configured: nothing to call."""
        api = MagicMock()
        api.agent_kv_finalize.return_value = {
            "finalized": True,
            "webhook_url": "",
            "status": "completed",
        }

        self._call_complete(cb_kwargs, api)

        mock_send_webhook.assert_not_called()

    @patch(_PATCH_SEND_WEBHOOK)
    def test_webhook_fires_from_error_link_too(self, mock_send_webhook, cb_kwargs):
        from ide_callback.agent_kv_tasks import agent_kv_error

        api = MagicMock()
        api.agent_kv_finalize.return_value = {
            "finalized": True,
            "webhook_url": "https://example.com/hook",
            "status": "failed",
        }

        with (
            patch(_PATCH_GET_CLIENT, return_value=api),
            patch(_PATCH_ASYNC_RESULT, return_value=MagicMock(result=None)),
        ):
            agent_kv_error("failed-task-5", cb_kwargs)

        mock_send_webhook.assert_called_once_with(
            "https://example.com/hook",
            {"job_id": "job-1", "status": "failed"},
            allow_insecure=False,
        )
