"""Unit tests for the Prompt Studio cancellation signal (UN-1031).

The rules pinned here are the ones every other layer trusts: a per-prompt Stop
must not abort the rest of the run, a whole-run Stop must abort everything, and
an unreachable Redis must read as "not cancelled" so a healthy run is never
killed by a cache outage.
"""

import unittest
from unittest import mock

from unstract.core import prompt_run_cancellation as prc


class FakeRedis:
    """Minimal stand-in for the set operations the module uses."""

    def __init__(self, fail: bool = False):
        self.sets: dict[str, set[str]] = {}
        self.expiries: dict[str, int] = {}
        self.fail = fail

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    def sadd(self, key, *members):
        self._check()
        self.sets.setdefault(key, set()).update(members)

    def expire(self, key, ttl):
        self._check()
        self.expiries[key] = ttl

    def smembers(self, key):
        self._check()
        return set(self.sets.get(key, set()))

    def delete(self, key):
        self._check()
        self.sets.pop(key, None)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, client: FakeRedis):
        self.client = client
        self.ops: list = []

    def sadd(self, key, *members):
        self.ops.append(lambda: self.client.sadd(key, *members))

    def expire(self, key, ttl):
        self.ops.append(lambda: self.client.expire(key, ttl))

    def execute(self):
        for op in self.ops:
            op()
        self.ops.clear()


ORG = "org1"
RUN = "11111111-1111-1111-1111-111111111111"
PROMPT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROMPT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class PromptRunCancellationTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        patcher = mock.patch.object(prc, "_get_client", return_value=self.fake)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_key_is_scoped_by_org_and_run(self):
        self.assertEqual(prc.cancel_key(ORG, RUN), f"ps:cancel:{ORG}:{RUN}")
        self.assertNotEqual(prc.cancel_key("other", RUN), prc.cancel_key(ORG, RUN))

    def test_whole_run_cancel_stops_everything(self):
        self.assertTrue(prc.request_cancel(ORG, RUN))
        self.assertTrue(prc.is_cancelled(ORG, RUN))
        self.assertTrue(prc.is_cancelled(ORG, RUN, PROMPT_A))
        self.assertTrue(prc.is_cancelled(ORG, RUN, PROMPT_B))

    def test_empty_prompt_ids_is_treated_as_whole_run(self):
        self.assertTrue(prc.request_cancel(ORG, RUN, []))
        self.assertEqual(prc.cancelled_prompt_ids(ORG, RUN), frozenset({prc.WHOLE_RUN}))

    def test_per_prompt_cancel_leaves_the_rest_of_the_run_alone(self):
        prc.request_cancel(ORG, RUN, [PROMPT_A])
        self.assertTrue(prc.is_cancelled(ORG, RUN, PROMPT_A))
        self.assertFalse(prc.is_cancelled(ORG, RUN, PROMPT_B))
        # No prompt named: shared stages (extract/index) must NOT be aborted,
        # because the run's other prompts still depend on them.
        self.assertFalse(prc.is_cancelled(ORG, RUN))

    def test_per_prompt_cancels_accumulate(self):
        prc.request_cancel(ORG, RUN, [PROMPT_A])
        prc.request_cancel(ORG, RUN, [PROMPT_B])
        self.assertEqual(
            prc.cancelled_prompt_ids(ORG, RUN), frozenset({PROMPT_A, PROMPT_B})
        )

    def test_cancel_sets_a_ttl_outliving_the_executor_lease(self):
        prc.request_cancel(ORG, RUN)
        self.assertEqual(
            self.fake.expiries[prc.cancel_key(ORG, RUN)], prc.CANCEL_TTL_SECONDS
        )
        # Must outlive the chart's 7200s executor visibility timeout, else a late
        # checkpoint would miss the intent.
        self.assertGreaterEqual(prc.CANCEL_TTL_SECONDS, 7200)

    def test_unknown_run_is_not_cancelled(self):
        self.assertFalse(prc.is_cancelled(ORG, "no-such-run"))
        self.assertEqual(prc.cancelled_prompt_ids(ORG, "no-such-run"), frozenset())

    def test_blank_run_id_is_not_cancelled(self):
        self.assertEqual(prc.cancelled_prompt_ids(ORG, ""), frozenset())
        self.assertFalse(prc.is_cancelled(ORG, ""))

    def test_clear_cancel_removes_the_intent(self):
        prc.request_cancel(ORG, RUN)
        prc.clear_cancel(ORG, RUN)
        self.assertFalse(prc.is_cancelled(ORG, RUN))

    def test_cancel_is_scoped_per_tenant(self):
        prc.request_cancel(ORG, RUN)
        self.assertFalse(prc.is_cancelled("other-org", RUN))


class RedisUnavailableTests(unittest.TestCase):
    """A cache outage must never kill a healthy run, and never raise."""

    def test_reads_degrade_to_not_cancelled(self):
        with mock.patch.object(prc, "_get_client", return_value=FakeRedis(fail=True)):
            self.assertFalse(prc.is_cancelled(ORG, RUN))
            self.assertEqual(prc.cancelled_prompt_ids(ORG, RUN), frozenset())

    def test_request_cancel_reports_failure_rather_than_raising(self):
        with mock.patch.object(prc, "_get_client", return_value=FakeRedis(fail=True)):
            self.assertFalse(prc.request_cancel(ORG, RUN))

    def test_no_client_is_handled_everywhere(self):
        with mock.patch.object(prc, "_get_client", return_value=None):
            self.assertFalse(prc.request_cancel(ORG, RUN))
            self.assertFalse(prc.is_cancelled(ORG, RUN))
            self.assertEqual(prc.cancelled_prompt_ids(ORG, RUN), frozenset())
            prc.clear_cancel(ORG, RUN)  # must not raise

    def test_clear_cancel_swallows_errors(self):
        with mock.patch.object(prc, "_get_client", return_value=FakeRedis(fail=True)):
            prc.clear_cancel(ORG, RUN)  # must not raise


class SentinelContractTests(unittest.TestCase):
    def test_whole_run_sentinel_cannot_collide_with_an_id(self):
        # Prompt ids are UUIDs; "*" is not a legal UUID character sequence.
        self.assertEqual(prc.WHOLE_RUN, "*")

    def test_error_text_is_the_shared_sentinel(self):
        # Matched by the consumer, the callbacks and the socket handler — a
        # reword here without updating them would silently turn every cancel
        # back into a "failed" run.
        self.assertEqual(prc.PROMPT_RUN_CANCELLED_ERROR, "Prompt run cancelled by user")


if __name__ == "__main__":
    unittest.main()
