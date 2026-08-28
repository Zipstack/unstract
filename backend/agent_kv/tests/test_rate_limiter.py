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
    m_redis.return_value.zcard.return_value = 2
    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is True
    assert m_redis.return_value.zadd.called


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
def test_key_rate_over_limit(m_redis):
    m_redis.return_value.incr.return_value = 61
    assert rl.check_key_rate("key1") is False


@mock.patch.object(rl, "_redis")
def test_key_rate_under_limit(m_redis):
    m_redis.return_value.incr.return_value = 3
    assert rl.check_key_rate("key1") is True
