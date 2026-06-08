"""Unit tests for the shared clubbed-notification renderer.

``build_envelope`` / ``render_slack_text`` produce the receiver-visible payload
for both the backend and the worker, so the envelope shape, the single-event
legacy-compat spread, the batch cap, and the Slack overflow footer are pinned
here (pure functions — no DB / Django needed).
"""

import unittest

from unstract.core.notification_clubbed_renderer import (
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


class RenderSlackTextTests(unittest.TestCase):
    def test_single_event_header_is_singular(self):
        text = render_slack_text(
            build_envelope([_payload(status="ERROR", failed_files=1, total_files=2)])
        )
        self.assertIn("*1 execution*", text)
        self.assertIn("1 failed", text)

    def test_overflow_footer_collapses_extra_events(self):
        payloads = [
            _payload(execution_id=f"e{i}") for i in range(SLACK_MAX_DISPLAY_EVENTS + 1)
        ]
        text = render_slack_text(build_envelope(payloads))
        # 26 events, 25 shown → exactly 1 collapsed under the footer.
        self.assertIn("and 1 more executions", text)


if __name__ == "__main__":
    unittest.main()
