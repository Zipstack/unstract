"""Recording a key's use in Redis and flushing it to the daily tables."""

import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from unittest import mock

from account_v2.models import Organization
from django.db import OperationalError
from django.test import TestCase, override_settings
from django_redis import get_redis_connection
from redis.sentinel import Sentinel, SentinelConnectionPool

from api_key_usage import flush as flush_module
from api_key_usage import recorder
from api_key_usage.constants import (
    BATCH_PREFIX,
    BATCHES_KEY,
    BATCH_FAILURES_KEY,
    DEAD_BATCHES_KEY,
    FLUSH_DUE_KEY,
    FLUSH_LOCK_KEY,
    MAX_BATCH_ATTEMPTS,
    PENDING_CALLS,
    PENDING_HASHES,
    RETENTION_DAYS,
)
from api_key_usage.flush import _take_pending, flush_pending_usage
from api_key_usage.models import (
    ApiKeyCallerDaily,
    ApiKeyLastUsed,
    ApiKeyUsageAppliedBatch,
    ApiKeyUsageDaily,
)
from api_key_usage.recorder import record_key_use
from api_key_usage.tests.redis_state import clear_usage_redis
from api_key_usage.recorder import start_background_flush as REAL_START_BACKGROUND_FLUSH

KEY_TYPE = "platform_api_key"
# Recent days, so a flush's retention prune keeps them whenever the tests run.
_TODAY = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
DAY_1 = _TODAY - timedelta(days=2, hours=-9, minutes=-30)
DAY_2 = _TODAY - timedelta(days=1, hours=-23, minutes=-59)
DEPLOYMENT = uuid.uuid4()


class UsageTestBase(TestCase):
    def setUp(self) -> None:
        self.redis = get_redis_connection("default")
        self._clear_redis()
        self.addCleanup(self._clear_redis)
        # Recording schedules a background flush; tests flush explicitly.
        patcher = mock.patch.object(recorder, "start_background_flush")
        self.start_flush = patcher.start()
        self.addCleanup(patcher.stop)
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        self.key_id = uuid.uuid4()

    def _clear_redis(self) -> None:
        clear_usage_redis()

    def record(self, at: datetime = DAY_1, **kwargs) -> None:
        kwargs.setdefault("key_type", KEY_TYPE)
        kwargs.setdefault("key_id", self.key_id)
        kwargs.setdefault("organization_id", self.org.pk)
        record_key_use(at=at, **kwargs)

    def daily(self, key_id=None) -> dict[date, int]:
        rows = ApiKeyUsageDaily.objects.filter(key_id=key_id or self.key_id)
        return {row.day: row.calls for row in rows}


class RecordAndFlushTests(UsageTestBase):
    def test_recording_writes_nothing_to_the_database_until_a_flush(self) -> None:
        self.record()

        self.assertFalse(ApiKeyUsageDaily.objects.exists())
        self.assertFalse(ApiKeyLastUsed.objects.exists())

    def test_flush_writes_daily_counts_and_last_used(self) -> None:
        self.record(at=DAY_1)
        self.record(at=DAY_1 + timedelta(hours=1))
        self.record(at=DAY_2)

        result = flush_pending_usage()

        self.assertEqual(result.calls, 3)
        self.assertEqual(self.daily(), {DAY_1.date(): 2, DAY_2.date(): 1})
        last = ApiKeyLastUsed.objects.get(key_id=self.key_id)
        self.assertEqual(last.last_used_at, DAY_2)
        self.assertEqual(last.organization, self.org)
        self.assertEqual(last.key_type, KEY_TYPE)

    def test_a_later_flush_adds_to_the_day_already_written(self) -> None:
        self.record()
        flush_pending_usage()
        self.record()
        self.record()

        flush_pending_usage()

        self.assertEqual(self.daily(), {DAY_1.date(): 3})

    def test_a_late_recording_does_not_replace_a_newer_pending_use(self) -> None:
        # A request that took its time first but records last.
        self.record(at=DAY_2, api_deployment_id=DEPLOYMENT)
        self.record(at=DAY_1, api_deployment_id=DEPLOYMENT)

        flush_pending_usage()

        self.assertEqual(ApiKeyLastUsed.objects.get().last_used_at, DAY_2)
        self.assertEqual(
            ApiKeyCallerDaily.objects.get(day=DAY_2.date()).last_call_at, DAY_2
        )

    def test_last_used_never_moves_backwards(self) -> None:
        self.record(at=DAY_2)
        flush_pending_usage()
        self.record(at=DAY_1)

        flush_pending_usage()

        self.assertEqual(ApiKeyLastUsed.objects.get().last_used_at, DAY_2)

    def test_days_are_utc_days(self) -> None:
        # 23:59 UTC on Oct 2 is already Oct 3 in Kolkata; the count stays on Oct 2.
        self.record(at=DAY_2.astimezone(timezone(timedelta(hours=5, minutes=30))))

        flush_pending_usage()

        self.assertEqual(self.daily(), {DAY_2.date(): 1})

    def test_keys_are_counted_separately(self) -> None:
        other = uuid.uuid4()
        self.record()
        self.record(key_id=other)
        self.record(key_id=other)

        flush_pending_usage()

        self.assertEqual(self.daily(), {DAY_1.date(): 1})
        self.assertEqual(self.daily(other), {DAY_1.date(): 2})

    def test_a_flush_with_nothing_pending_writes_nothing(self) -> None:
        result = flush_pending_usage()

        self.assertFalse(result.skipped)
        self.assertEqual(result.calls, 0)
        self.assertFalse(ApiKeyUsageDaily.objects.exists())


class CallerTests(UsageTestBase):
    def test_a_deployment_call_records_its_caller(self) -> None:
        deployment = uuid.uuid4()
        self.record(at=DAY_1, api_deployment_id=deployment)
        self.record(at=DAY_1 + timedelta(hours=2), api_deployment_id=deployment)

        flush_pending_usage()

        caller = ApiKeyCallerDaily.objects.get()
        self.assertEqual(caller.api_deployment_id, deployment)
        self.assertEqual(caller.calls, 2)
        self.assertEqual(caller.last_call_at, DAY_1 + timedelta(hours=2))
        self.assertEqual(caller.day, DAY_1.date())
        self.assertEqual(self.daily(), {DAY_1.date(): 2})

    def test_a_call_without_a_deployment_records_no_caller(self) -> None:
        self.record()

        flush_pending_usage()

        self.assertFalse(ApiKeyCallerDaily.objects.exists())

    def test_callers_accumulate_across_flushes(self) -> None:
        deployment = uuid.uuid4()
        self.record(at=DAY_1 + timedelta(hours=3), api_deployment_id=deployment)
        flush_pending_usage()
        self.record(at=DAY_1, api_deployment_id=deployment)

        flush_pending_usage()

        caller = ApiKeyCallerDaily.objects.get()
        self.assertEqual(caller.calls, 2)
        self.assertEqual(caller.last_call_at, DAY_1 + timedelta(hours=3))


class FlushTriggerTests(UsageTestBase):
    def test_the_first_use_in_an_interval_starts_one_flush(self) -> None:
        self.record()
        self.record()
        self.record()

        self.start_flush.assert_called_once_with()

    @override_settings(API_KEY_USAGE_FLUSH_INTERVAL_SECONDS=120)
    def test_the_trigger_expires_after_the_flush_interval(self) -> None:
        self.record()

        ttl = self.redis.ttl(FLUSH_DUE_KEY)
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, 120)

    def test_a_use_after_the_interval_starts_another_flush(self) -> None:
        self.record()
        self.redis.delete(FLUSH_DUE_KEY)  # the interval ran out

        self.record()

        self.assertEqual(self.start_flush.call_count, 2)

    def test_a_flush_that_cannot_start_does_not_fail_the_request(self) -> None:
        self.start_flush.side_effect = RuntimeError("can't start new thread")

        with self.assertLogs("api_key_usage.recorder", "ERROR"):
            self.record()

        self.assertEqual(
            self.redis.hlen(PENDING_HASHES[0]), 1, "the use waits for the next flush"
        )

    def test_the_background_flush_writes_the_usage(self) -> None:
        with mock.patch.object(recorder.connection, "close") as close:
            self.record()
            recorder._flush_and_close()

        self.assertEqual(self.daily(), {DAY_1.date(): 1})
        close.assert_called_once_with()

    def test_no_thread_starts_while_background_flush_is_off(self) -> None:
        with (
            override_settings(API_KEY_USAGE_BACKGROUND_FLUSH=False),
            mock.patch.object(recorder.threading, "Thread") as thread,
        ):
            REAL_START_BACKGROUND_FLUSH()

        thread.assert_not_called()

    def test_a_thread_starts_while_background_flush_is_on(self) -> None:
        with (
            override_settings(API_KEY_USAGE_BACKGROUND_FLUSH=True),
            mock.patch.object(recorder.threading, "Thread") as thread,
        ):
            REAL_START_BACKGROUND_FLUSH()

        thread.return_value.start.assert_called_once_with()

    def test_a_failing_background_flush_is_logged_not_raised(self) -> None:
        with (
            mock.patch.object(
                flush_module, "flush_pending_usage", side_effect=RuntimeError("db down")
            ),
            mock.patch.object(recorder.connection, "close"),
            self.assertLogs(recorder.logger, "ERROR"),
        ):
            recorder._flush_and_close()


class FailureTests(UsageTestBase):
    def test_recording_waits_on_redis_for_a_short_time_only(self) -> None:
        with (
            mock.patch.object(recorder, "_client", None),
            override_settings(API_KEY_USAGE_REDIS_TIMEOUT_SECONDS=0.25),
        ):
            kwargs = recorder._redis().connection_pool.connection_kwargs

        self.assertEqual(kwargs["socket_timeout"], 0.25)
        self.assertEqual(kwargs["socket_connect_timeout"], 0.25)

    def test_the_flush_waits_on_redis_for_a_short_time_only(self) -> None:
        # A read flushes first; a stalled Redis must fail that flush, not hang it.
        with (
            mock.patch.object(recorder, "_client", None),
            override_settings(API_KEY_USAGE_REDIS_TIMEOUT_SECONDS=0.25),
        ):
            flush_pending_usage()
            kwargs = recorder._client.connection_pool.connection_kwargs

        self.assertEqual(kwargs["socket_timeout"], 0.25)

    def test_the_sentinel_master_lookup_waits_a_short_time_only(self) -> None:
        sentinel = Sentinel([("sentinel.internal", 26379)])
        with (
            mock.patch.object(recorder, "_client", None),
            mock.patch.object(
                recorder,
                "get_redis_connection",
                return_value=sentinel.master_for("mymaster"),
            ),
            override_settings(API_KEY_USAGE_REDIS_TIMEOUT_SECONDS=0.25),
        ):
            pool = recorder._redis().connection_pool

        self.assertIsInstance(pool, SentinelConnectionPool)
        for client in pool.sentinel_manager.sentinels:
            kwargs = client.connection_pool.connection_kwargs
            self.assertEqual(kwargs["socket_timeout"], 0.25)
            self.assertEqual(kwargs["socket_connect_timeout"], 0.25)

    def test_a_redis_outage_is_logged_once_a_minute(self) -> None:
        with (
            mock.patch.object(recorder, "_redis", side_effect=ConnectionError("down")),
            mock.patch.object(recorder, "_last_failure_logged", 0.0),
            mock.patch.object(recorder, "_failures_since_logged", 0),
            self.assertLogs(recorder.logger, "ERROR") as logs,
        ):
            for _ in range(3):
                self.record()

        self.assertEqual(len(logs.output), 1)

    def test_a_redis_failure_never_reaches_the_caller(self) -> None:
        with (
            mock.patch.object(recorder, "_redis", side_effect=ConnectionError("down")),
            mock.patch.object(recorder, "_last_failure_logged", 0.0),
            self.assertLogs(recorder.logger, "ERROR"),
        ):
            self.record()

        self.start_flush.assert_not_called()

    def test_a_failed_write_keeps_the_batch_for_the_next_flush(self) -> None:
        self.record(api_deployment_id=uuid.uuid4())
        self.record()

        with (
            mock.patch.object(
                flush_module, "_write", side_effect=RuntimeError("db down")
            ),
            self.assertLogs(flush_module.logger, "ERROR"),
        ):
            result = flush_pending_usage()
        self.assertEqual(result.failed, 1)
        self.assertFalse(ApiKeyUsageDaily.objects.exists())

        flush_pending_usage()

        self.assertEqual(self.daily(), {DAY_1.date(): 2})
        self.assertEqual(ApiKeyCallerDaily.objects.get().calls, 1)
        self.assertEqual(ApiKeyLastUsed.objects.get().last_used_at, DAY_1)

    def test_a_batch_left_by_a_killed_flush_is_applied_by_the_next(self) -> None:
        self.record(api_deployment_id=DEPLOYMENT)
        _take_pending(self.redis, "killed")  # moved aside, then the process died
        self.record()

        result = flush_pending_usage()

        self.assertEqual((result.batches, result.calls, result.callers), (2, 2, 1))
        self.assertEqual(self.daily(), {DAY_1.date(): 2})
        self.assertEqual(ApiKeyCallerDaily.objects.get().calls, 1)
        self.assertFalse(self.redis.exists(BATCHES_KEY))
        self.assertFalse(list(self.redis.scan_iter(f"{BATCH_PREFIX}:*")))

    def test_a_batch_already_written_is_never_added_twice(self) -> None:
        # Its write committed, then the flush died before clearing Redis.
        self.record()
        _take_pending(self.redis, "written")
        ApiKeyUsageAppliedBatch.objects.create(token="written")

        result = flush_pending_usage()

        self.assertEqual((result.batches, result.calls), (0, 0))
        self.assertFalse(ApiKeyUsageDaily.objects.exists())
        self.assertFalse(self.redis.exists(BATCHES_KEY))

    def test_a_use_moves_aside_whole_with_its_caller(self) -> None:
        self.record(api_deployment_id=DEPLOYMENT)

        _take_pending(self.redis, "t")

        self.assertFalse(any(self.redis.exists(name) for name in PENDING_HASHES))
        self.assertEqual(
            len(list(self.redis.scan_iter(f"{BATCH_PREFIX}:t:*"))),
            len(PENDING_HASHES),
        )

    def test_a_failed_flush_releases_its_lock(self) -> None:
        with (
            mock.patch.object(flush_module, "_take_pending", side_effect=RuntimeError),
            self.assertRaises(RuntimeError),
        ):
            self.record()
            flush_pending_usage()

        self.assertFalse(self.redis.exists(FLUSH_LOCK_KEY))

    def test_a_flush_skips_while_another_holds_the_lock(self) -> None:
        self.record()
        self.redis.set(FLUSH_LOCK_KEY, "someone-else")

        result = flush_pending_usage()

        self.assertTrue(result.skipped)
        self.assertFalse(ApiKeyUsageDaily.objects.exists())
        self.assertEqual(self.redis.get(FLUSH_LOCK_KEY), b"someone-else")
        self.assertTrue(self.redis.exists(PENDING_CALLS))

    def test_usage_of_a_deleted_organisation_is_dropped(self) -> None:
        gone = Organization.objects.create(
            name="org-gone", display_name="Gone", organization_id="org-gone"
        )
        self.record(organization_id=gone.pk, key_id=uuid.uuid4())
        gone.delete()
        self.record()

        result = flush_pending_usage()

        self.assertEqual(result.dropped, 2)  # its count and its last-used
        self.assertEqual(self.daily(), {DAY_1.date(): 1})

    def test_a_failing_batch_does_not_hold_up_the_others(self) -> None:
        self.record()
        _take_pending(self.redis, "a-bad")
        self.record(key_id=uuid.uuid4())
        real_write = flush_module._write

        def write(pending, result):
            if len(pending.calls) == 1 and str(self.key_id) in next(iter(pending.calls)):
                raise RuntimeError("bad batch")
            real_write(pending, result)

        with (
            mock.patch.object(flush_module, "_write", side_effect=write),
            self.assertLogs(flush_module.logger, "ERROR"),
        ):
            result = flush_pending_usage()

        self.assertEqual((result.failed, result.batches, result.calls), (1, 1, 1))
        self.assertEqual(self.redis.smembers(BATCHES_KEY), {b"a-bad"})

    def test_a_batch_that_keeps_failing_is_set_aside(self) -> None:
        self.record()
        _take_pending(self.redis, "bad")

        with (
            mock.patch.object(flush_module, "_write", side_effect=RuntimeError),
            self.assertLogs(flush_module.logger, "ERROR") as logs,
        ):
            results = [flush_pending_usage() for _ in range(MAX_BATCH_ATTEMPTS)]

        self.assertEqual([r.set_aside for r in results][-1], 1)
        self.assertEqual(sum(r.set_aside for r in results), 1)
        self.assertIn("set aside", logs.output[-1])
        self.assertFalse(self.redis.exists(BATCHES_KEY))
        self.assertEqual(self.redis.smembers(DEAD_BATCHES_KEY), {b"bad"})
        name = f"{BATCH_PREFIX}:bad:{PENDING_CALLS}"
        self.assertGreater(self.redis.ttl(name), 0)  # kept, but not for ever
        self.assertEqual(flush_pending_usage().failed, 0)

    def test_a_batch_that_times_out_each_time_is_set_aside(self) -> None:
        # A statement timeout or deadlock with both connections working is the
        # batch's fault, not an outage, so it must not hold up the others.
        self.record()
        _take_pending(self.redis, "a-bad")
        real_write = flush_module._write

        def write(pending, result):
            if any(str(self.key_id) in f for f in pending.calls):
                raise OperationalError("canceling statement due to statement timeout")
            real_write(pending, result)

        with (
            mock.patch.object(flush_module, "_write", side_effect=write),
            mock.patch.object(flush_module, "_prune", return_value=0) as prune,
            self.assertLogs(flush_module.logger, "ERROR") as logs,
        ):
            results = []
            for _ in range(MAX_BATCH_ATTEMPTS):
                self.record(key_id=uuid.uuid4())
                results.append(flush_pending_usage())

        self.assertEqual([r.batches for r in results], [1] * MAX_BATCH_ATTEMPTS)
        self.assertEqual(prune.call_count, MAX_BATCH_ATTEMPTS)
        self.assertEqual(results[-1].set_aside, 1)
        self.assertIn("set aside", logs.output[-1])
        self.assertEqual(self.redis.smembers(DEAD_BATCHES_KEY), {b"a-bad"})

    def test_an_outage_never_sets_a_batch_aside(self) -> None:
        self.record()
        _take_pending(self.redis, "a")
        self.record()
        _take_pending(self.redis, "b")
        write = mock.Mock(side_effect=OperationalError("connection refused"))

        with (
            mock.patch.object(flush_module, "_write", write),
            mock.patch.object(flush_module, "_backends_up", return_value=False),
            mock.patch.object(flush_module, "_prune") as prune,
            self.assertLogs(flush_module.logger, "WARNING"),
        ):
            results = [flush_pending_usage() for _ in range(MAX_BATCH_ATTEMPTS + 2)]

        self.assertEqual(sum(r.set_aside for r in results), 0)
        self.assertEqual(write.call_count, MAX_BATCH_ATTEMPTS + 2)  # stops at once
        prune.assert_not_called()
        self.assertFalse(self.redis.exists(BATCH_FAILURES_KEY))
        self.assertFalse(self.redis.exists(DEAD_BATCHES_KEY))
        self.assertEqual(self.redis.smembers(BATCHES_KEY), {b"a", b"b"})

        result = flush_pending_usage()  # the outage is over
        self.assertEqual((result.failed, result.batches), (0, 2))

    def test_a_field_with_a_bad_part_is_dropped(self) -> None:
        bad = [
            f"{KEY_TYPE}|not-a-uuid|{self.org.pk}|{DAY_1.date()}",
            f"{KEY_TYPE}|{uuid.uuid4()}|not-an-org|{DAY_1.date()}",
            f"{KEY_TYPE}|{uuid.uuid4()}|{self.org.pk}|not-a-day",
        ]
        for fld in bad:
            self.redis.hincrby(PENDING_CALLS, fld, 1)
        self.record()

        with self.assertLogs(flush_module.logger, "WARNING"):
            result = flush_pending_usage()

        self.assertEqual((result.dropped, result.failed), (3, 0))
        self.assertEqual(self.daily(), {DAY_1.date(): 1})

    def test_a_malformed_field_is_dropped_not_retried(self) -> None:
        self.redis.hincrby(PENDING_CALLS, "not-a-valid-field", 1)
        self.record()

        with self.assertLogs(flush_module.logger, "WARNING"):
            result = flush_pending_usage()

        self.assertEqual(result.dropped, 1)
        self.assertEqual(self.daily(), {DAY_1.date(): 1})
        self.assertFalse(self.redis.exists(PENDING_CALLS))


class RetentionTests(UsageTestBase):
    def test_a_flush_prunes_days_outside_the_retention_window(self) -> None:
        now = datetime(2026, 10, 31, 12, tzinfo=UTC)
        oldest_kept = now.date() - timedelta(days=RETENTION_DAYS - 1)
        for day in (oldest_kept - timedelta(days=1), oldest_kept):
            ApiKeyUsageDaily.objects.create(
                organization=self.org,
                key_type=KEY_TYPE,
                key_id=self.key_id,
                day=day,
                calls=5,
            )
            ApiKeyCallerDaily.objects.create(
                organization=self.org,
                key_type=KEY_TYPE,
                key_id=self.key_id,
                api_deployment_id=uuid.uuid4(),
                day=day,
                calls=5,
                last_call_at=now,
            )

        with mock.patch.object(flush_module.timezone, "now", return_value=now):
            result = flush_pending_usage()

        self.assertEqual(result.pruned, 2)
        self.assertEqual(self.daily(), {oldest_kept: 5})
        self.assertEqual(
            list(ApiKeyCallerDaily.objects.values_list("day", flat=True)),
            [oldest_kept],
        )

    def test_last_used_is_kept_beyond_the_window(self) -> None:
        # Idle (over 90 days unused) needs last used long after the counts expire.
        self.record(at=DAY_1)
        flush_pending_usage()
        later = DAY_1 + timedelta(days=200)

        with mock.patch.object(flush_module.timezone, "now", return_value=later):
            flush_pending_usage()

        self.assertFalse(ApiKeyUsageDaily.objects.exists())
        self.assertEqual(ApiKeyLastUsed.objects.get().last_used_at, DAY_1)
