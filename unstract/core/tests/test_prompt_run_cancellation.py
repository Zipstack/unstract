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
        self.strings: dict[str, str] = {}
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

    def set(self, key, value, ex=None, nx=False):
        self._check()
        if nx and key in self.strings:
            return None
        self.strings[key] = value
        if ex is not None:
            self.expiries[key] = ex
        return True

    def get(self, key):
        self._check()
        return self.strings.get(key)

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


class TestRunOwnership(unittest.TestCase):
    """The run -> tool binding a cancel is authorised against (UN-1031).

    Run ids arrive from the browser, so the binding has to be immutable: an
    overwritable record would be no protection at all, since a caller could
    rebind someone else's live run to a tool they control and cancel it
    through that tool (raised by Greptile on PR #2283).
    """

    def setUp(self):
        self.redis = FakeRedis()
        self.patcher = mock.patch.object(prc, "_get_client", return_value=self.redis)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_first_writer_takes_the_binding(self):
        assert prc.remember_run_owner("org", "run-1", "tool-a") is True
        assert prc.run_owner("org", "run-1") == "tool-a"

    def test_another_tool_cannot_rebind_a_live_run(self):
        prc.remember_run_owner("org", "run-1", "tool-a")

        assert prc.remember_run_owner("org", "run-1", "tool-b") is False
        # The original owner survives, so a cancel through tool-b is refused.
        assert prc.run_owner("org", "run-1") == "tool-a"

    def test_the_same_tool_may_rebind_its_own_run(self):
        """A retry or a second dispatch under the same run id is legitimate."""
        prc.remember_run_owner("org", "run-1", "tool-a")

        assert prc.remember_run_owner("org", "run-1", "tool-a") is True

    def test_an_unreachable_store_never_blocks_a_dispatch(self):
        """Fail open: refusing to start work because Redis blinked would be
        far worse than leaving one run unverifiable.
        """
        self.redis.fail = True

        assert prc.remember_run_owner("org", "run-1", "tool-a") is True
        assert prc.run_owner("org", "run-1") is None

    def test_an_unknown_run_has_no_owner(self):
        assert prc.run_owner("org", "never-dispatched") is None


class TestClientBuildIsThreadSafe(unittest.TestCase):
    """Django serves requests on several threads, so the lazily built client
    must be built once, not once per racing thread (raised in review).
    """

    def setUp(self):
        prc._client_singleton = None
        prc._client_last_failure = None
        self.addCleanup(setattr, prc, "_client_singleton", None)
        self.addCleanup(setattr, prc, "_client_last_failure", None)

    def test_racing_threads_build_the_client_once(self):
        import threading
        import time

        builds = []

        def slow_factory(**_kwargs):
            # Widen the window so an unguarded check-then-build would race.
            builds.append(1)
            time.sleep(0.05)
            return mock.MagicMock(name="redis")

        barrier = threading.Barrier(8)
        results = []

        def worker():
            barrier.wait()
            results.append(prc._get_client())

        with mock.patch.object(prc, "create_redis_client", side_effect=slow_factory):
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        assert len(builds) == 1
        assert len({id(r) for r in results}) == 1
