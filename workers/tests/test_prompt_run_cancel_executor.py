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


class TestLookupEnrichmentStop:
    """Lookup enrichment is a billable LLM call with an outbound webhook right
    behind it, so a stop has to be honoured there too (raised by QA).
    """

    def test_a_stop_is_not_reported_as_a_lookup_failure(self):
        """The handler degrades gracefully on plugin drift. A stop is not
        drift, and must not be logged as "lookup failed".
        """
        from executor.executors.lookup_enrichment import run_lookup_enrichment

        lookup_cls = MagicMock()
        lookup_cls.run_with_metrics.side_effect = AbortedError("stopped mid-call")
        shim = MagicMock()

        with (
            patch(
                "executor.executors.lookup_enrichment.ExecutorPluginLoader.get",
                return_value=lookup_cls,
            ),
            pytest.raises(AbortedError),
        ):
            run_lookup_enrichment(
                output={PSKeys.NAME: "field_a", "lookup_config": {"lookup_name": "L"}},
                structured_output={"field_a": "a value"},
                metadata={},
                metrics={},
                shim=shim,
                usage_kwargs={},
                llm_cls=MagicMock(),
            )

        # And nothing told the user the lookup broke.
        assert not any(
            "failed" in str(call).lower() for call in shim.stream_log.call_args_list
        )

    def test_plugin_failures_are_still_swallowed(self):
        """The graceful-degradation contract this handler exists for."""
        from executor.executors.lookup_enrichment import run_lookup_enrichment

        lookup_cls = MagicMock()
        lookup_cls.run_with_metrics.side_effect = TypeError("plugin contract drift")

        with patch(
            "executor.executors.lookup_enrichment.ExecutorPluginLoader.get",
            return_value=lookup_cls,
        ):
            records = run_lookup_enrichment(
                output={PSKeys.NAME: "field_a", "lookup_config": {"lookup_name": "L"}},
                structured_output={"field_a": "a value"},
                metadata={},
                metrics={},
                shim=MagicMock(),
                usage_kwargs={},
                llm_cls=MagicMock(),
            )

        assert records == []

    def test_a_stop_lands_before_the_lookup_and_its_webhook(self, executor_env):
        """The webhook fires immediately after enrichment and cannot be taken
        back once another system has received it, so the checkpoint has to sit
        in front of both — not after them.

        The stop is timed to land *after* the model has answered, so the only
        checkpoint that can catch it is the new one. A run stopped earlier
        would never reach this part of the prompt at all, and would prove
        nothing about it.
        """
        from executor.executors import legacy_executor as le

        answered = {"yet": False}
        llm = _mock_llm()
        answer = llm.complete.return_value

        def _answer_then_stop(*_args, **_kwargs):
            answered["yet"] = True
            return answer

        llm.complete.side_effect = _answer_then_stop
        prompts = [_prompt("field_a", PROMPT_A)]

        with (
            patch(
                "executor.executors.legacy_executor.LegacyExecutor._get_prompt_deps",
                return_value=_mock_deps(llm),
            ),
            patch.object(le, "run_lookup_enrichment", return_value=[]) as lookup,
            patch.object(le, "run_webhook_postprocessing") as webhook,
            patch(
                "executor.executors.legacy_executor.is_cancelled",
                side_effect=lambda *a, **k: answered["yet"],
            ),
        ):
            result = executor_env()._handle_answer_prompt(_context(prompts))

        # The prompt really did run — so the stop landed mid-prompt, not before.
        assert answered["yet"] is True
        assert result.metadata["cancelled_prompt_ids"] == [PROMPT_A]
        # ...and neither the billable lookup nor the irreversible webhook ran.
        lookup.assert_not_called()
        webhook.assert_not_called()

    def test_an_unstopped_run_still_enriches_and_posts(self, executor_env):
        from executor.executors import legacy_executor as le

        prompts = [_prompt("field_a", PROMPT_A)]
        with (
            patch.object(le, "run_lookup_enrichment", return_value=[]) as lookup,
            patch.object(le, "run_webhook_postprocessing") as webhook,
            patch("executor.executors.legacy_executor.is_cancelled", return_value=False),
        ):
            executor_env()._handle_answer_prompt(_context(prompts))

        lookup.assert_called_once()
        webhook.assert_called_once()


class TestIndexCleanupIsScopedToThisRun:
    """A stop must not delete an index this run never wrote (code review).

    ``is_document_indexed`` embeds a query to probe the vector store, and that
    embedding call is itself abortable. By then ``doc_id`` already names a
    document a PREVIOUS run may have indexed completely — so cleaning up on
    that path destroys good vectors.
    """

    @staticmethod
    def _index_context() -> ExecutionContext:
        return ExecutionContext(
            executor_name="legacy",
            operation=Operation.INDEX.value,
            executor_params={
                "embedding_instance_id": "emb-1",
                "vector_db_instance_id": "vdb-1",
                "x2text_instance_id": "x2t-1",
                "file_path": "/tmp/doc.pdf",
                "file_hash": "hash",
                "extracted_text": "some extracted text",
                "platform_api_key": "pk",
                "tool_id": "tool-1",
            },
            run_id="run-1",
            execution_source="ide",
            organization_id="org-1",
        )

    def _run_with_abort_at(self, executor_env, *, abort_during_probe: bool):
        """Abort either during the existence probe or during real indexing."""
        from executor.executors import legacy_executor as le

        index = MagicMock()
        index.generate_index_key.return_value = "doc-id-1"
        if abort_during_probe:
            index.is_document_indexed.side_effect = AbortedError("stopped")
        else:
            index.is_document_indexed.return_value = False
            index.perform_indexing.side_effect = AbortedError("stopped")

        with (
            patch.object(
                le.LegacyExecutor,
                "_get_indexing_deps",
                return_value=(MagicMock(return_value=index), MagicMock(), MagicMock()),
            ),
            # Storage is env-configured and irrelevant here.
            patch(
                "executor.executors.legacy_executor.FileUtils.get_fs_instance",
                return_value=MagicMock(),
            ),
            patch("executor.executors.legacy_executor.is_cancelled", return_value=False),
        ):
            executor_env().execute(self._index_context())
        return index

    def test_a_stop_during_the_existence_probe_deletes_nothing(self, executor_env):
        """The dangerous case: the document is already fully indexed."""
        index = self._run_with_abort_at(executor_env, abort_during_probe=True)

        index.delete_nodes.assert_not_called()

    def test_a_stop_while_writing_still_cleans_up(self, executor_env):
        """The case the cleanup exists for must keep working."""
        index = self._run_with_abort_at(executor_env, abort_during_probe=False)

        index.delete_nodes.assert_called_once()


class TestStoppedProgressCount:
    def test_a_whole_run_stop_does_not_count_unreached_prompts_as_done(
        self, executor_env
    ):
        """A whole-run stop breaks the loop, so prompts it never reached are in
        neither list. Subtracting counted them as answered (code review).
        """
        prompts = [
            _prompt("field_a", PROMPT_A),
            _prompt("field_b", PROMPT_B),
            _prompt("field_c", PROMPT_C),
        ]
        shim = MagicMock()
        with (
            patch(
                "executor.executors.legacy_executor.ExecutorToolShim", return_value=shim
            ),
            patch(
                "executor.executors.legacy_executor.is_cancelled",
                side_effect=_stop_run_except(PROMPT_A),
            ),
        ):
            executor_env()._handle_answer_prompt(_context(prompts))

        said = " ".join(str(c) for c in shim.stream_log.call_args_list)
        # One prompt answered before the stop; C was never reached.
        assert "Stopped by user after 1 of 3 prompts" in said
        assert "2 of 3" not in said
