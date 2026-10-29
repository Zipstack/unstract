"""Recording a key's use in Redis and flushing it to the daily tables."""

import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from unittest import mock

from account_v2.models import Organization
from django.test import TestCase, override_settings
from django_redis import get_redis_connection

from api_key_usage import flush as flush_module
from api_key_usage import recorder
from api_key_usage.constants import (
    BATCH_PREFIX,
    BATCHES_KEY,
    FLUSH_DUE_KEY,
    FLUSH_LOCK_KEY,
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
from api_key_usage.recorder import start_background_flush as REAL_START_BACKGROUND_FLUSH

KEY_TYPE = "platform_api_key"
DAY_1 = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
DAY_2 = datetime(2026, 10, 2, 23, 59, tzinfo=UTC)
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
        batches = list(self.redis.scan_iter(f"{BATCH_PREFIX}:*"))
        self.redis.delete(
            *PENDING_HASHES, *batches, BATCHES_KEY, FLUSH_DUE_KEY, FLUSH_LOCK_KEY
        )

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
    def test_a_redis_failure_never_reaches_the_caller(self) -> None:
        with (
            mock.patch.object(
                recorder, "get_redis_connection", side_effect=ConnectionError("down")
            ),
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
            self.assertRaises(RuntimeError),
        ):
            flush_pending_usage()
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
            mock.patch.object(flush_module, "_write", side_effect=RuntimeError),
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
