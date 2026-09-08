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
from unstract.sdk1.utils.aborting import AbortedError, should_abort_now

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


class TestInFlightAbort:
    """The second layer: a stop that lands *inside* a call, not between them.

    The checkpoints above stop the next call. These pin what happens when
    there is no next call to stop — the user pressed Stop while a model was
    already taking minutes to answer, and the SDK abandoned the request.
    """

    def test_an_abandoned_call_is_reported_as_a_stop_not_a_failure(self, executor_env):
        """`AbortedError` is the SDK's word for it; every layer past the
        executor only knows `ExecutionCancelled`.
        """
        llm = _mock_llm()
        llm.complete.side_effect = AbortedError("stopped mid-call")
        prompts = [_prompt("field_a", PROMPT_A)]

        with (
            patch(
                "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps",
                return_value=_mock_deps(llm),
            ),
            patch("executor.executors.legacy_executor.is_cancelled", return_value=False),
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        # Not an error: reporting failure would send the callback down the
        # error path and throw away the rest of the batch.
        assert result.success is True
        assert result.metadata["cancelled_prompt_ids"] == [PROMPT_A]
        # And no half-finished answer is passed off as a real one.
        assert "field_a" not in result.data[PSKeys.OUTPUT]

    def test_the_sdk_learns_of_the_stop_through_the_ambient_scope(self, executor_env):
        """The executor never hands the SDK a prompt id — it installs a scoped
        predicate and the SDK polls it. This is the wiring that makes a Stop
        aimed at one prompt abandon only that prompt's call.
        """
        llm = _mock_llm()
        answer = llm.complete.return_value

        def _complete(*_args, **_kwargs):
            # Stand in for litellm: notice the caller stopped waiting.
            if should_abort_now():
                raise AbortedError("caller stopped waiting")
            return answer

        llm.complete.side_effect = _complete
        prompts = [_prompt("field_a", PROMPT_A), _prompt("field_b", PROMPT_B)]

        def _only_b(org_id, run_id, prompt_id=None):
            return prompt_id == PROMPT_B

        with (
            patch(
                "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps",
                return_value=_mock_deps(llm),
            ),
            patch("executor.executors.legacy_executor.is_cancelled", side_effect=_only_b),
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        assert "field_a" in result.data[PSKeys.OUTPUT]
        assert result.metadata["cancelled_prompt_ids"] == [PROMPT_B]

    def test_tokens_spent_before_the_abort_still_reach_the_usage_rows(self, executor_env):
        """Abandoning the request does not refund what it already cost."""
        llm = _mock_llm()
        llm.complete.side_effect = AbortedError("stopped mid-call")
        llm.flush_pending_usage.return_value = [{"prompt_tokens": 4096}]
        prompts = [_prompt("field_a", PROMPT_A)]

        with (
            patch(
                "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps",
                return_value=_mock_deps(llm),
            ),
            patch("executor.executors.legacy_executor.is_cancelled", return_value=False),
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        assert {"prompt_tokens": 4096} in result.metadata["usage_records"]

    def test_summarization_stopped_by_the_user_is_not_a_summarization_failure(
        self, executor_env
    ):
        """Summarize has one broad handler that would otherwise relabel a stop
        as an error, and the run would surface as failed rather than stopped.
        """
        ctx = ExecutionContext(
            executor_name="legacy",
            operation=Operation.SUMMARIZE.value,
            executor_params={
                "llm_adapter_instance_id": "llm-1",
                "summarize_prompt": "summarize",
                PSKeys.CONTEXT: "a very long document",
                "prompt_keys": ["field_a"],
                PSKeys.PLATFORM_SERVICE_API_KEY: "pk",
            },
            run_id="run-1",
            execution_source="ide",
            organization_id="org-1",
        )
        with (
            patch("executor.executors.legacy_executor.is_cancelled", return_value=False),
            patch(
                "executor.executors.answer_prompt.AnswerPromptService.run_completion",
                side_effect=AbortedError("stopped mid-call"),
            ),
        ):
            result = executor_env().execute(ctx)

        assert result.success is False
        assert result.error == PROMPT_RUN_CANCELLED_ERROR


class TestAbortPredicate:
    def test_workflow_runs_get_no_predicate_at_all(self, executor_env):
        """No Stop button on that path; a predicate would be pure overhead on
        every poll of every call.
        """
        from executor.executors.legacy_executor import LegacyExecutor

        assert LegacyExecutor._abort_check(_context([], execution_source="tool")) is None
        assert callable(LegacyExecutor._abort_check(_context([])))

    def test_a_negative_answer_is_memoized(self):
        """The SDK polls twice a second. A fifteen-minute extraction would
        otherwise be eighteen hundred round trips to the signal store.
        """
        from executor.executors.legacy_executor import LegacyExecutor

        with patch(
            "executor.executors.legacy_executor.is_cancelled", return_value=False
        ) as is_cancelled:
            check = LegacyExecutor._abort_check(_context([]))
            answers = [check() for _ in range(20)]

        assert answers == [False] * 20
        assert is_cancelled.call_count == 1

    def test_a_stop_is_never_rescinded(self):
        from executor.executors.legacy_executor import LegacyExecutor

        with patch(
            "executor.executors.legacy_executor.is_cancelled", side_effect=[True, False]
        ):
            check = LegacyExecutor._abort_check(_context([]))
            assert check() is True
            # A second, contradicting answer must not un-stop the run.
            assert check() is True
