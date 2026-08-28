import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv import rate_limiter as rl  # noqa: E402


@mock.patch.object(rl, "_redis")
def test_acquire_under_limit(m_redis):
    mock_redis = m_redis.return_value
    mock_redis.zcard.return_value = 2

    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is True

    key = "agent_kv:inflight:org1"

    assert mock_redis.zremrangebyscore.call_args[0][0] == key
    assert mock_redis.zcard.call_args[0][0] == key
    zadd_args = mock_redis.zadd.call_args[0]
    assert zadd_args[0] == key
    assert "job1" in zadd_args[1]

    # Self-heal-before-check-before-acquire ordering is a constraint.
    call_names = [c[0] for c in mock_redis.method_calls]
    assert (
        call_names.index("zremrangebyscore")
        < call_names.index("zcard")
        < call_names.index("zadd")
    )


@mock.patch.object(rl, "_redis")
def test_acquire_at_limit_refused(m_redis):
    m_redis.return_value.zcard.return_value = 5
    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is False
    assert not m_redis.return_value.zadd.called


@mock.patch.object(rl, "_redis")
def test_release_removes_member(m_redis):
    rl.AgentKVConcurrencyLimiter.release("org1", "job1")
    m_redis.return_value.zrem.assert_called_once_with(
        "agent_kv:inflight:org1", "job1"
    )


@mock.patch.object(rl, "_redis")
def test_redis_error_fails_open(m_redis):
    m_redis.return_value.zcard.side_effect = ConnectionError("down")
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
