"""Cooperative cancellation inside the legacy executor (UN-1031).

Nothing can interrupt this task from outside — the consumer runs it eagerly,
in-process, with no revoke and no time limit — so the pipeline stops only where
it asks to. What matters, and is pinned here:

* a bulk run is ONE task looping over many prompts, so stopping it must keep
  the answers already paid for rather than throw the whole batch away;
* stopping one prompt must not stop the others;
* tokens already spent before the stop must still reach the usage rows;
* a stop must not look like a failure, or the callback discards the results.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.exceptions import ExecutionCancelled

from unstract.core.prompt_run_cancellation import PROMPT_RUN_CANCELLED_ERROR
from unstract.sdk1.execution.context import ExecutionContext, Operation

from .test_answer_prompt import _make_prompt, _mock_deps, _mock_llm

PROMPT_A = "11111111-1111-1111-1111-111111111111"
PROMPT_B = "22222222-2222-2222-2222-222222222222"
PROMPT_C = "33333333-3333-3333-3333-333333333333"


def _prompt(name, prompt_id):
    out = _make_prompt(name=name)
    out[PSKeys.PROMPT_ID] = prompt_id
    return out


def _context(prompts, execution_source="ide", run_id="run-1"):
    params = {
        PSKeys.OUTPUTS: prompts,
        PSKeys.TOOL_SETTINGS: {},
        PSKeys.TOOL_ID: "tool-1",
        PSKeys.EXECUTION_ID: "exec-1",
        PSKeys.FILE_HASH: "hash",
        PSKeys.FILE_PATH: "/tmp/doc.txt",
        PSKeys.FILE_NAME: "doc.txt",
        PSKeys.LOG_EVENTS_ID: "",
        PSKeys.CUSTOM_DATA: {},
        PSKeys.EXECUTION_SOURCE: execution_source,
        PSKeys.PLATFORM_SERVICE_API_KEY: "pk-test",
    }
    return ExecutionContext(
        executor_name="legacy",
        operation=Operation.ANSWER_PROMPT.value,
        executor_params=params,
        run_id=run_id,
        execution_source=execution_source,
        organization_id="org-1",
    )


@pytest.fixture(autouse=True)
def _mock_indexing_utils():
    """``generate_index_key`` reaches the platform service over HTTP, which a
    mock shim cannot satisfy. Same guard as ``test_answer_prompt``.
    """
    with patch(
        "unstract.sdk1.utils.indexing.IndexingUtils.generate_index_key",
        return_value="doc-id-test",
    ):
        yield


@pytest.fixture
def executor_env():
    """Patch the executor's heavy deps; yield the LegacyExecutor class."""
    from executor.executors.legacy_executor import LegacyExecutor

    with (
        patch(
            "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps"
        ) as deps,
        patch("executor.executors.legacy_executor.ExecutorToolShim") as shim,
    ):
        deps.return_value = _mock_deps(_mock_llm())
        shim.return_value = MagicMock()
        yield LegacyExecutor


def _stop_run_except(*allowed):
    """A whole-run stop that lets *allowed* prompts through first.

    Deterministic on purpose: keyed on the prompt id rather than a call count,
    so it does not silently change meaning when a checkpoint is added or moved.
    Answers yes to the un-named (whole-run) query too, which is what makes the
    loop break instead of skipping a single prompt.
    """

    def _stub(org_id, run_id, prompt_id=None):
        return prompt_id not in allowed

    return _stub


class TestWholeRunStop:
    def test_keeps_the_prompts_that_finished(self, executor_env):
        prompts = [
            _prompt("field_a", PROMPT_A),
            _prompt("field_b", PROMPT_B),
            _prompt("field_c", PROMPT_C),
        ]
        # Let the first prompt through, then stop.
        with patch(
            "executor.executors.legacy_executor.is_cancelled",
            side_effect=_stop_run_except(PROMPT_A),
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        assert result.success is True
        # The answer the user already paid for survives...
        assert "field_a" in result.data[PSKeys.OUTPUT]
        # ...and the ones that never ran are reported, not silently missing.
        assert result.metadata["cancelled"] is True
        assert PROMPT_B in result.metadata["cancelled_prompt_ids"]

    def test_reports_success_so_the_callback_persists_the_partial(self, executor_env):
        prompts = [_prompt("field_a", PROMPT_A), _prompt("field_b", PROMPT_B)]
        with patch(
            "executor.executors.legacy_executor.is_cancelled",
            side_effect=_stop_run_except(PROMPT_A),
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        # Reporting failure would send the callback down the error path and
        # throw away every completed prompt.
        assert result.success is True
        assert result.error is None

    def test_stops_the_loop_rather_than_skipping_one_prompt(self, executor_env):
        prompts = [
            _prompt("field_a", PROMPT_A),
            _prompt("field_b", PROMPT_B),
            _prompt("field_c", PROMPT_C),
        ]
        with patch(
            "executor.executors.legacy_executor.is_cancelled",
            side_effect=_stop_run_except(PROMPT_A),
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        # B is the prompt the stop lands on; C is never attempted at all, so
        # the run reports exactly one cancelled prompt rather than "all the
        # rest".
        assert result.metadata["cancelled_prompt_ids"] == [PROMPT_B]
        assert "field_c" not in result.data[PSKeys.OUTPUT]


class TestPerPromptStop:
    def test_other_prompts_keep_running(self, executor_env):
        prompts = [_prompt("field_a", PROMPT_A), _prompt("field_b", PROMPT_B)]

        def _only_b(org_id, run_id, prompt_id=None):
            return prompt_id == PROMPT_B

        with patch(
            "executor.executors.legacy_executor.is_cancelled", side_effect=_only_b
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        assert result.success is True
        assert "field_a" in result.data[PSKeys.OUTPUT]  # untouched
        assert result.metadata["cancelled_prompt_ids"] == [PROMPT_B]


class TestNoCancel:
    def test_clean_run_carries_no_cancel_metadata(self, executor_env):
        prompts = [_prompt("field_a", PROMPT_A)]
        with patch("executor.executors.legacy_executor.is_cancelled", return_value=False):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        assert result.success is True
        assert "cancelled" not in result.metadata

    def test_workflow_runs_never_consult_the_signal_store(self, executor_env):
        prompts = [_prompt("field_a", PROMPT_A)]
        with patch(
            "executor.executors.legacy_executor.is_cancelled", return_value=True
        ) as is_cancelled:
            result = executor_env()._handle_answer_prompt(
                _context(prompts, execution_source="tool")
            )

        # The workflow path has no user-facing Stop; paying for a lookup per
        # prompt there would be pure overhead.
        is_cancelled.assert_not_called()
        assert result.success is True


class TestCheckpointContract:
    def test_cancelled_error_carries_the_shared_sentinel(self):
        # Every layer (consumer, callbacks, UI) matches on this exact text to
        # tell a stop apart from a failure.
        assert ExecutionCancelled().message == PROMPT_RUN_CANCELLED_ERROR

    def test_extract_stops_before_the_billable_call(self, executor_env):
        from executor.executors.legacy_executor import LegacyExecutor

        ctx = ExecutionContext(
            executor_name="legacy",
            operation=Operation.EXTRACT.value,
            executor_params={
                "x2text_instance_id": "x2t-1",
                "file_path": "/tmp/doc.pdf",
                "platform_api_key": "pk",
            },
            run_id="run-1",
            execution_source="ide",
            organization_id="org-1",
        )
        with (
            patch("executor.executors.legacy_executor.is_cancelled", return_value=True),
            patch("executor.executors.legacy_executor.X2Text") as x2text,
        ):
            result = LegacyExecutor().execute(ctx)

        # The adapter can block for 15 minutes with no way back out, so the
        # check has to happen before it is ever constructed/called.
        x2text.return_value.process.assert_not_called()
        assert result.success is False
        assert result.error == PROMPT_RUN_CANCELLED_ERROR
