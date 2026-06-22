"""Unit tests for the pure statistics + transport-classification layer."""

from __future__ import annotations

import math

import pytest

from pg_benchmark.db import ExecutionLatency, Transport
from pg_benchmark.stats import percentile, summarize


class TestPercentile:
    def test_endpoints_are_min_and_max(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert percentile(values, 0) == 1.0
        assert percentile(values, 100) == 5.0

    def test_median_of_odd_sample(self):
        assert percentile([3.0, 1.0, 2.0], 50) == 2.0

    def test_median_of_even_sample_interpolates(self):
        assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5

    def test_p95_interpolates_between_ranks(self):
        # 0..100 step 1 → p95 lands exactly on 95 (rank 95 of 100).
        values = [float(i) for i in range(101)]
        assert percentile(values, 95) == pytest.approx(95.0)

    def test_single_element(self):
        assert percentile([7.0], 50) == 7.0
        assert percentile([7.0], 99) == 7.0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            percentile([], 50)


class TestSummarize:
    def test_empty_sample_is_all_zero(self):
        s = summarize([])
        assert s.empty
        assert s.n == 0 and s.mean == 0.0 and s.p99 == 0.0

    def test_basic_summary(self):
        s = summarize([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert s.n == 8
        assert s.mean == pytest.approx(5.0)
        assert s.minimum == 2.0 and s.maximum == 9.0
        assert s.stdev == pytest.approx(2.0)  # population stdev of this classic sample

    def test_single_value_has_zero_stdev(self):
        s = summarize([3.3])
        assert s.n == 1 and s.stdev == 0.0 and s.p50 == 3.3


class TestTransportClassify:
    def test_pg_wins_when_queue_message_present(self):
        assert (
            Transport.classify(has_queue_message_id=True, has_task_id=True)
            is Transport.PG
        )

    def test_celery_when_only_task_id(self):
        assert (
            Transport.classify(has_queue_message_id=False, has_task_id=True)
            is Transport.CELERY
        )

    def test_inline_when_neither(self):
        assert (
            Transport.classify(has_queue_message_id=False, has_task_id=False)
            is Transport.INLINE
        )


class TestParallelism:
    def _exec(self, *, exec_time, file_times):
        return ExecutionLatency(
            execution_id="x",
            transport=Transport.PG,
            status="COMPLETED",
            total_files=len(file_times),
            server_execution_time=exec_time,
            file_times=file_times,
        )

    def test_fully_parallel_two_files_is_near_two(self):
        # Two 30s files that overlapped → execution ~34s → ratio ≈ 1.76.
        e = self._exec(exec_time=34.0, file_times=[29.9, 29.8])
        assert e.parallelism == pytest.approx(59.7 / 34.0)
        assert e.parallelism > 1.5

    def test_serial_two_files_is_near_one(self):
        e = self._exec(exec_time=60.0, file_times=[30.0, 30.0])
        assert e.parallelism == pytest.approx(1.0)

    def test_none_when_no_files(self):
        assert self._exec(exec_time=10.0, file_times=[]).parallelism is None

    def test_none_when_no_exec_time(self):
        e = self._exec(exec_time=None, file_times=[1.0])
        assert e.parallelism is None

    def test_is_terminal(self):
        assert self._exec(exec_time=1.0, file_times=[1.0]).is_terminal


def test_stdev_matches_math():
    values = [1.0, 2.0, 3.0]
    s = summarize(values)
    expected = math.sqrt(((1 - 2) ** 2 + 0 + (3 - 2) ** 2) / 3)
    assert s.stdev == pytest.approx(expected)
