"""Unit tests for the shared clubbed-notification renderer.

``build_envelope`` / ``render_slack_text`` produce the receiver-visible payload
for both the backend and the worker, so the envelope shape, the single-event
legacy-compat spread, the batch cap, and the Slack overflow footer are pinned
here (pure functions — no DB / Django needed).
"""

import unittest

from unstract.core.notification_clubbed_renderer import (
    _MISSING,
    MAX_BATCH_SIZE,
    SLACK_MAX_DISPLAY_EVENTS,
    build_envelope,
    render_slack_text,
)


def _payload(status="COMPLETED", failed_files=0, total_files=3, **overrides):
    """A buffered per-event payload dict (the shape build_envelope consumes)."""
    payload = {
        "type": "API",
        "pipeline_id": "pipe-1",
        "pipeline_name": "demo",
        "status": status,
        "execution_id": "exec-1",
        "error_message": None,
        "timestamp": "2026-05-11T11:38:31",
        "additional_data": {
            "total_files": total_files,
            "successful_files": total_files - failed_files,
            "failed_files": failed_files,
        },
    }
    payload.update(overrides)
    return payload


class BuildEnvelopeTests(unittest.TestCase):
    def test_summary_counts_use_failure_predicate(self):
        env = build_envelope(
            [
                _payload(status="ERROR", failed_files=0, total_files=0),  # status fail
                _payload(status="COMPLETED", failed_files=2, total_files=5),  # partial
                _payload(status="COMPLETED", failed_files=0, total_files=5),  # success
            ]
        )
        self.assertEqual(env["summary"], {"total": 3, "succeeded": 1, "failed": 2})

    def test_single_event_spreads_legacy_flat_keys(self):
        env = build_envelope(
            [
                _payload(
                    status="ERROR",
                    failed_files=1,
                    total_files=2,
                    error_message="boom",
                )
            ]
        )
        # Canonical envelope still present alongside the legacy flat keys.
        self.assertIn("summary", env)
        self.assertIn("events", env)
        self.assertEqual(env["type"], "API")
        self.assertEqual(env["pipeline_id"], "pipe-1")
        self.assertEqual(env["pipeline_name"], "demo")
        self.assertEqual(env["status"], "ERROR")
        self.assertEqual(env["execution_id"], "exec-1")
        self.assertEqual(env["error_message"], "boom")
        # The two worker-callback-only legacy keys (raw values, not humanized).
        self.assertEqual(env["timestamp"], "2026-05-11T11:38:31")
        self.assertEqual(
            env["additional_data"],
            {"total_files": 2, "successful_files": 1, "failed_files": 1},
        )

    def test_multi_event_is_envelope_only(self):
        env = build_envelope([_payload(), _payload(execution_id="exec-2")])
        self.assertEqual(set(env), {"summary", "events"})

    def test_batch_is_capped_at_max_batch_size(self):
        env = build_envelope(
            [_payload(execution_id=f"e{i}") for i in range(MAX_BATCH_SIZE + 5)]
        )
        self.assertEqual(env["summary"]["total"], MAX_BATCH_SIZE)
        self.assertEqual(len(env["events"]), MAX_BATCH_SIZE)

    def test_event_timestamp_is_humanized(self):
        # _humanize_timestamp interpolates dt.day rather than the %-d directive
        # (which raises on macOS/Windows) — pin the receiver-visible string.
        env = build_envelope([_payload()])
        self.assertEqual(env["events"][0]["timestamp"], "2026 May 11 11:38:31 AM")

    def test_unparseable_timestamp_falls_back_without_raising(self):
        env = build_envelope([_payload(timestamp="not-a-timestamp")])
        self.assertEqual(env["events"][0]["timestamp"], _MISSING)

    def test_error_message_absent_from_success_event(self):
        # _event_from_payload sets error_message only when truthy.
        env = build_envelope([_payload(status="COMPLETED", failed_files=0)])
        self.assertNotIn("error_message", env["events"][0])

    def test_empty_batch_is_envelope_only(self):
        env = build_envelope([])
        self.assertEqual(env["summary"], {"total": 0, "succeeded": 0, "failed": 0})
        self.assertEqual(env["events"], [])
        self.assertEqual(set(env), {"summary", "events"})

    def test_explicit_is_failure_overrides_unclassifiable_status(self):
        # The regression: the backend pipeline path sends PipelineStatus vocab
        # ("FAILURE") that is_failure_run can't classify, with failed_files=0
        # (deploy/setup error before any file ran). The explicit verdict the
        # dispatch site carries must still count it as a failure.
        env = build_envelope(
            [_payload(status="FAILURE", failed_files=0, total_files=0, is_failure=True)]
        )
        self.assertEqual(env["summary"], {"total": 1, "succeeded": 0, "failed": 1})
        self.assertIs(env["events"][0]["is_failure"], True)

    def test_explicit_is_failure_false_is_authoritative(self):
        # A False verdict wins even when the status string looks like a failure.
        env = build_envelope(
            [_payload(status="ERROR", failed_files=0, is_failure=False)]
        )
        self.assertEqual(env["summary"], {"total": 1, "succeeded": 1, "failed": 0})

    def test_absent_flag_falls_back_to_predicate_and_omits_key(self):
        # Worker / legacy payloads carry no flag: classification falls back to
        # is_failure_run(status, failed_files) and the event dict stays free of
        # the key (byte-identical to pre-change output).
        env = build_envelope([_payload(status="ERROR", failed_files=0)])
        self.assertEqual(env["summary"]["failed"], 1)
        self.assertNotIn("is_failure", env["events"][0])


class RenderSlackTextTests(unittest.TestCase):
    def test_single_event_header_is_singular(self):
        text = render_slack_text(
            build_envelope([_payload(status="ERROR", failed_files=1, total_files=2)])
        )
        self.assertIn("*1 execution*", text)
        self.assertIn("1 failed", text)

    def test_explicit_failure_flag_drives_header_and_event_emoji(self):
        # End-to-end of the regression on the Slack side: a FAILURE-vocab run
        # with 0 failed files renders as failed (header + per-event glyph),
        # not the success ✅ it showed before the explicit verdict was carried.
        text = render_slack_text(
            build_envelope(
                [
                    _payload(
                        status="FAILURE",
                        failed_files=0,
                        total_files=0,
                        is_failure=True,
                    )
                ]
            )
        )
        self.assertIn("1 failed", text)
        self.assertIn(":x: 0/0 files", text)

    def test_overflow_footer_collapses_extra_events(self):
        payloads = [
            _payload(execution_id=f"e{i}") for i in range(SLACK_MAX_DISPLAY_EVENTS + 1)
        ]
        text = render_slack_text(build_envelope(payloads))
        # 26 events, 25 shown → exactly 1 collapsed under the footer.
        self.assertIn("and 1 more executions", text)

    def test_empty_batch_header_renders(self):
        text = render_slack_text(build_envelope([]))
        self.assertIn("*0 executions*", text)

    def test_file_count_column_omitted_when_no_totals(self):
        # The "N/M files" column appears only when additional_data has totals;
        # an empty additional_data collapses the line (5 fields, not 6).
        with_counts = render_slack_text(
            build_envelope([_payload(total_files=3, failed_files=1)])
        )
        self.assertIn("files", with_counts)
        without_counts = render_slack_text(
            build_envelope([_payload(additional_data={})])
        )
        self.assertNotIn("files", without_counts)


if __name__ == "__main__":
    unittest.main()
