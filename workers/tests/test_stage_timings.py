"""Tests for per-file workflow stage timing capture (UN-3451).

Covers the tool-split derivation (including the agentic double-count trap) and
the collector's contract: accumulation, recording a stage that raised, and a
payload that stays well-formed against garbage input.
"""

import time

import pytest

from shared.workflow.execution.stage_timings import (
    STAGE_TIMINGS_VERSION,
    StageTimingCollector,
    ToolStage,
    WorkflowStage,
    tool_split_from_metrics,
)
from unstract.core.stage_timings import aggregate_stage_timings


def _legacy_metrics():
    """Metrics as the legacy (non-agentic) structure pipeline reports them."""
    return {
        "_file": {"text_extraction": {"time_taken(s)": 8.92}},
        "invoice_number": {
            "indexing": {"time_taken(s)": 2.0},
            "context_retrieval": {"time_taken(s)": 0.2},
            "extraction_llm": {"time_taken(s)": 3.0},
        },
        "total_amount": {
            "indexing": {"time_taken(s)": 1.1},
            "context_retrieval": {"time_taken(s)": 0.35},
            "extraction_llm": {"time_taken(s)": 2.75},
        },
    }


class TestToolSplitFromMetrics:
    def test_sums_per_prompt_figures_into_three_buckets(self):
        split = tool_split_from_metrics(_legacy_metrics())

        assert split[ToolStage.EXTRACTION] == 8.92
        assert split[ToolStage.INDEXING] == pytest.approx(3.1)
        # context_retrieval + extraction_llm across both prompts
        assert split[ToolStage.PROMPTS] == pytest.approx(6.3)

    def test_agentic_text_extraction_is_not_double_counted(self):
        """An agentic prompt's extraction time is already folded into _file.

        _merge_agentic_metrics adds each agentic prompt's text_extraction into
        the file-level bucket and reports the total it folded; subtracting that
        exact amount is what stops the same seconds being counted twice. The
        nesting below mirrors production: the prompt's figure lives under
        ``table_extraction``, not directly on the prompt bucket.
        """
        metrics = {
            "_file": {"text_extraction": {"time_taken(s)": 5.0}},
            "line_items": {
                "table_extraction": {
                    "text_extraction": {"time_taken(s)": 5.0},
                    "llm": {"time_taken(s)": 1.5},
                }
            },
        }

        split = tool_split_from_metrics(metrics, agentic_extraction_seconds=5.0)

        assert split[ToolStage.EXTRACTION] == 5.0
        assert split[ToolStage.PROMPTS] == 1.5

    def test_unfolded_table_extraction_time_is_kept(self):
        """The non-agentic table plugin's extraction was never folded into _file.

        It writes to the same `prompt -> table_extraction` path as the agentic
        route, so excluding every sub-tree named `text_extraction` would drop
        this time from every bucket and silently inflate `unaccounted` — worst
        on smart-table runs, where `_file.text_extraction` is absent entirely.
        """
        metrics = {
            "line_items": {
                "table_extraction": {
                    "text_extraction": {"time_taken(s)": 4.0},
                    "llm": {"time_taken(s)": 1.0},
                }
            },
        }

        split = tool_split_from_metrics(metrics, agentic_extraction_seconds=0.0)

        assert split[ToolStage.PROMPTS] == 5.0
        assert ToolStage.EXTRACTION not in split

    def test_folded_amount_never_drives_prompts_negative(self):
        metrics = {"a": {"extraction_llm": {"time_taken(s)": 1.0}}}

        split = tool_split_from_metrics(metrics, agentic_extraction_seconds=99.0)

        assert ToolStage.PROMPTS not in split

    @pytest.mark.parametrize("folded", [None, "nope", -3.0, True])
    def test_unusable_folded_amount_is_ignored(self, folded):
        metrics = {"a": {"extraction_llm": {"time_taken(s)": 2.0}}}

        split = tool_split_from_metrics(metrics, agentic_extraction_seconds=folded)

        assert split[ToolStage.PROMPTS] == 2.0

    def test_nested_plugin_metrics_are_walked(self):
        """Plugin sub-trees nest arbitrarily; every time_taken(s) counts."""
        metrics = {
            "line_items": {
                "line_item_extraction": {
                    "pass_1": {"llm": {"time_taken(s)": 1.0}},
                    "pass_2": {"llm": {"time_taken(s)": 2.0}},
                }
            }
        }

        assert tool_split_from_metrics(metrics)[ToolStage.PROMPTS] == 3.0

    @pytest.mark.parametrize("metrics", [None, {}, "nope", 42, []])
    def test_no_metrics_yields_no_split(self, metrics):
        """A Docker tool reports no split rather than a split of zeros."""
        assert tool_split_from_metrics(metrics) == {}

    def test_zero_buckets_are_omitted(self):
        metrics = {"field": {"extraction_llm": {"time_taken(s)": 1.0}}}

        split = tool_split_from_metrics(metrics)

        assert split == {ToolStage.PROMPTS: 1.0}

    def test_unusable_values_are_ignored(self):
        metrics = {
            "a": {"indexing": {"time_taken(s)": "slow"}},
            "b": {"indexing": {"time_taken(s)": True}},
            "c": {"indexing": {"time_taken(s)": -4.0}},
            "d": "not-a-dict",
            "e": {"indexing": {"time_taken(s)": 1.25}},
        }

        assert tool_split_from_metrics(metrics) == {ToolStage.INDEXING: 1.25}


class TestStageTimingCollector:
    def test_record_accumulates_repeat_calls(self):
        collector = StageTimingCollector()

        collector.record(WorkflowStage.SOURCE_FETCH, 1.0)
        collector.record(WorkflowStage.SOURCE_FETCH, 0.5)

        assert collector.to_dict()["stages"][WorkflowStage.SOURCE_FETCH] == 1.5

    def test_stage_context_manager_records_when_block_raises(self):
        """A stage that failed part-way still took the time it took."""
        collector = StageTimingCollector()

        with pytest.raises(RuntimeError):
            with collector.stage(WorkflowStage.TOOL_EXECUTION):
                raise RuntimeError("tool blew up")

        assert WorkflowStage.TOOL_EXECUTION in collector.to_dict()["stages"]

    def test_payload_shape(self):
        collector = StageTimingCollector(started_at=time.time() - 20)
        collector.record(WorkflowStage.SETUP, 0.3)
        collector.record(WorkflowStage.SOURCE_FETCH, 0.9)
        collector.record(WorkflowStage.TOOL_EXECUTION, 18.0)
        collector.record(WorkflowStage.DESTINATION, 0.25)
        collector.set_tool_split(_legacy_metrics())

        payload = collector.to_dict(total=20.0)

        assert payload["version"] == STAGE_TIMINGS_VERSION
        assert payload["total"] == 20.0
        assert payload["stages"][WorkflowStage.TOOL_EXECUTION] == 18.0
        assert payload["tool_split"][ToolStage.EXTRACTION] == 8.92
        assert payload["unaccounted"] == pytest.approx(0.55)
        # queue_wait is the backend's to add — the worker cannot measure it.
        assert WorkflowStage.QUEUE_WAIT not in payload["stages"]
        assert "started_at" in payload

    def test_unaccounted_omitted_when_stages_meet_or_exceed_total(self):
        collector = StageTimingCollector()
        collector.record(WorkflowStage.TOOL_EXECUTION, 10.0)

        payload = collector.to_dict(total=9.0)

        assert "unaccounted" not in payload

    def test_set_tool_split_tolerates_garbage(self):
        collector = StageTimingCollector()

        collector.set_tool_split({"x": {"indexing": {"time_taken(s)": object()}}})

        assert "tool_split" not in collector.to_dict()

    def test_tool_split_accumulates_across_calls(self):
        """Two structure tools in one workflow both contribute to the split."""
        collector = StageTimingCollector()

        collector.set_tool_split({"a": {"indexing": {"time_taken(s)": 1.0}}})
        collector.set_tool_split({"b": {"indexing": {"time_taken(s)": 2.0}}})

        assert collector.to_dict()["tool_split"][ToolStage.INDEXING] == 3.0


class TestMetricsKeysMatchTheExecutor:
    """The metric keys are duplicated, so assert they still agree.

    stage_timings.py cannot import the executor package (the workflow-execution
    service imports it), so the four keys are copied. A rename on the executor
    side would otherwise make tool_split_from_metrics return {} for every file,
    silently and permanently. The test package has no such import restriction,
    which is what makes a test the right place to enforce this.
    """

    def test_keys_match(self):
        from executor.executors.constants import PromptServiceConstants as PSKeys

        from shared.workflow.execution import stage_timings as st

        assert st._FILE_METRICS_KEY == PSKeys.FILE
        assert st._TEXT_EXTRACTION_KEY == PSKeys.TEXT_EXTRACTION
        assert st._TIME_TAKEN_KEY == PSKeys.TIME_TAKEN
        assert st._INDEXING_KEY == PSKeys.INDEXING_METRICS


class TestAggregateStageTimings:
    def test_sums_stages_and_splits_across_files(self):
        payloads = [
            {
                "stages": {WorkflowStage.TOOL_EXECUTION: 10.0, "queue_wait": 1.0},
                "tool_split": {ToolStage.EXTRACTION: 6.0},
                "total": 11.0,
            },
            {
                "stages": {WorkflowStage.TOOL_EXECUTION: 4.0, "queue_wait": 2.5},
                "tool_split": {ToolStage.EXTRACTION: 2.0},
                "total": 6.5,
            },
        ]

        result = aggregate_stage_timings(payloads)

        assert result["files"] == 2
        assert result["stages"][WorkflowStage.TOOL_EXECUTION] == 14.0
        assert result["stages"]["queue_wait"] == 3.5
        assert result["tool_split"][ToolStage.EXTRACTION] == 8.0
        assert result["total"] == 17.5

    def test_unaccounted_survives_aggregation(self):
        """Dropping it leaves the aggregate's rows not explaining its total.

        Each per-file payload satisfies sum(stages) + unaccounted == total; the
        aggregate has to keep that relation or the chart it feeds is drawn
        against a total its segments cannot reach.
        """
        payloads = [
            {"stages": {"tool_execution": 8.0}, "total": 10.0, "unaccounted": 2.0},
            {"stages": {"tool_execution": 3.0}, "total": 5.0, "unaccounted": 2.0},
        ]

        result = aggregate_stage_timings(payloads)

        assert result["unaccounted"] == 4.0
        assert sum(result["stages"].values()) + result["unaccounted"] == result["total"]

    def test_unaccounted_is_zero_not_missing_when_nothing_is_unaccounted(self):
        result = aggregate_stage_timings([{"stages": {"setup": 1.0}, "total": 1.0}])

        assert result["unaccounted"] == 0.0

    def test_malformed_payloads_are_skipped(self):
        result = aggregate_stage_timings(
            [None, "nope", {}, {"stages": {"setup": 1.0}}, {"stages": "bad"}]
        )

        assert result["files"] == 1
        assert result["stages"] == {"setup": 1.0}

    @pytest.mark.parametrize("payloads", [None, [], [None], [{}]])
    def test_no_timing_yields_empty(self, payloads):
        assert aggregate_stage_timings(payloads) == {}
