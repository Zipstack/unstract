import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.conf import settings  # noqa: E402

from agent_kv import rate_limiter as rl  # noqa: E402


@mock.patch.object(rl, "_redis")
@mock.patch.object(rl.time, "time", return_value=1_700_000_000.0)
def test_acquire_under_limit(m_time, m_redis):
    """Acquire is ONE atomic server-side script call (trim, count, add,
    expire) -- never a client-side ``ZCARD`` followed by ``ZADD``, which is a
    check-then-act race that let 6 concurrent submits through a limit of 5
    in the 13b integration run. The e2e concurrency scenario is the real
    proof; this pins the script's inputs.
    """
    mock_redis = m_redis.return_value
    mock_redis.eval.return_value = 1

    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is True

    key = "agent_kv:inflight:org1"
    mock_redis.eval.assert_called_once()
    args = mock_redis.eval.call_args[0]
    script, numkeys, called_key, member, now, ttl_cut, limit, expire = args
    assert script is rl.AgentKVConcurrencyLimiter._ACQUIRE_SCRIPT
    assert (numkeys, called_key, member) == (1, key, "job1")
    assert now == 1_700_000_000.0
    assert ttl_cut == 1_700_000_000.0 - rl._SLOT_TTL_SECONDS
    assert limit == settings.AGENT_KV_CONCURRENT_LIMIT
    assert expire == rl._SLOT_TTL_SECONDS
    # No client-side check-then-act calls remain.
    assert not mock_redis.zcard.called and not mock_redis.zadd.called
    # Self-heal-before-check-before-acquire ordering lives inside the script.
    body = script
    assert body.index("ZREMRANGEBYSCORE") < body.index("ZCARD") < body.index("ZADD")


@mock.patch.object(rl, "_redis")
def test_acquire_at_limit_refused(m_redis):
    m_redis.return_value.eval.return_value = 0
    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is False


@mock.patch.object(rl, "_redis")
def test_release_removes_member(m_redis):
    rl.AgentKVConcurrencyLimiter.release("org1", "job1")
    m_redis.return_value.zrem.assert_called_once_with("agent_kv:inflight:org1", "job1")


@mock.patch.object(rl, "_redis")
def test_redis_error_fails_open(m_redis):
    m_redis.return_value.eval.side_effect = ConnectionError("down")
    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is True


@mock.patch.object(rl, "_redis")
@mock.patch.object(rl.time, "time", return_value=1_700_000_000.0)
def test_key_rate_over_limit(m_time, m_redis):
    mock_redis = m_redis.return_value
    mock_redis.incr.return_value = 61

    assert rl.check_key_rate("key1") is False

    expected_window = int(1_700_000_000.0 // 60)
    expected_key = f"agent_kv:rate:key1:{expected_window}"
    mock_redis.incr.assert_called_once_with(expected_key)
    mock_redis.expire.assert_called_once_with(expected_key, 120)


@mock.patch.object(rl, "_redis")
@mock.patch.object(rl.time, "time", return_value=1_700_000_000.0)
def test_key_rate_under_limit(m_time, m_redis):
    mock_redis = m_redis.return_value
    mock_redis.incr.return_value = 3

    assert rl.check_key_rate("key1") is True

    expected_window = int(1_700_000_000.0 // 60)
    expected_key = f"agent_kv:rate:key1:{expected_window}"
    mock_redis.incr.assert_called_once_with(expected_key)
    mock_redis.expire.assert_called_once_with(expected_key, 120)
