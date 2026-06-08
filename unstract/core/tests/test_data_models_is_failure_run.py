"""Unit tests for ``is_failure_run`` — the single notification-routing predicate.

``is_failure_run`` is the one rule that decides whether a failure-only
notification fires and how the clubbed renderer tallies succeeded/failed, so
its truth table is pinned here (pure function — no DB / Django needed).
"""

import unittest

from unstract.core.data_models import ExecutionStatus, is_failure_run


class IsFailureRunTests(unittest.TestCase):
    def test_terminal_failure_statuses_are_failures(self):
        self.assertTrue(is_failure_run(ExecutionStatus.ERROR.value, 0))
        self.assertTrue(is_failure_run(ExecutionStatus.STOPPED.value, 0))

    def test_completed_with_no_failed_files_is_success(self):
        self.assertFalse(is_failure_run(ExecutionStatus.COMPLETED.value, 0))

    def test_completed_with_failed_files_is_partial_failure(self):
        # Partial-success runs land COMPLETED with failed_files > 0 — the status
        # check alone would miss them.
        self.assertTrue(is_failure_run(ExecutionStatus.COMPLETED.value, 2))

    def test_failed_files_none_defaults_to_zero(self):
        self.assertFalse(is_failure_run(ExecutionStatus.COMPLETED.value, None))

    def test_failure_status_overrides_zero_failed_files(self):
        self.assertTrue(is_failure_run(ExecutionStatus.ERROR.value, None))

    def test_unknown_or_missing_status_is_not_a_failure(self):
        self.assertFalse(is_failure_run("NOT_A_STATUS", 0))
        self.assertFalse(is_failure_run(None, 0))

    def test_unknown_status_with_failed_files_is_still_a_failure(self):
        # Even if the status string is unrecognised, a failed file fails the run.
        self.assertTrue(is_failure_run("NOT_A_STATUS", 1))


if __name__ == "__main__":
    unittest.main()
