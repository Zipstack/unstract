import os
import pathlib
from unittest import mock

import django
import pytest
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
    assert not mock_redis.zcard.called
    assert not mock_redis.zadd.called
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
def test_redis_error_during_the_script_fails_closed(m_redis):
    """Was `test_redis_error_fails_open`, asserting `is True`.

    It pinned the defect as the contract: an error mid-script removed the
    concurrency ceiling and the API kept accepting billable work. The failure
    now surfaces as a 429 at the caller (`RateLimited`), which is recoverable;
    an unbounded fan-out is not. See `AGENT_KV_LIMITER_FAIL_OPEN` for the
    deliberate waiver.
    """
    m_redis.return_value.eval.side_effect = ConnectionError("down")
    with mock.patch.object(settings, "AGENT_KV_LIMITER_FAIL_OPEN", False):
        assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is False


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


# ---------------------------------------------------------------------------
# Backend-unavailable behaviour. Both limiters used to `return True` on ANY
# Redis exception, which is the one failure mode invisible from outside: a
# Sentinel failover or pool exhaustion removed the concurrency ceiling AND the
# per-key rate ceiling simultaneously, while the API went on returning 202s for
# billable LLM work with only a per-request `logger.warning` to show for it.
# ---------------------------------------------------------------------------


@mock.patch.object(rl, "_redis", side_effect=OSError("redis down"))
def test_concurrency_limiter_fails_closed_by_default(m_redis):
    with mock.patch.object(settings, "AGENT_KV_LIMITER_FAIL_OPEN", False):
        assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is False


@mock.patch.object(rl, "_redis", side_effect=OSError("redis down"))
def test_key_rate_limiter_fails_closed_by_default(m_redis):
    with mock.patch.object(settings, "AGENT_KV_LIMITER_FAIL_OPEN", False):
        assert rl.check_key_rate("key1") is False


@mock.patch.object(rl, "_redis", side_effect=OSError("redis down"))
def test_limiters_fail_open_only_when_the_setting_says_so(m_redis):
    """The waiver stays available -- availability-over-accounting is a real
    operational choice -- but it has to be made deliberately, in config, rather
    than being the implicit behaviour of an `except` block.
    """
    with mock.patch.object(settings, "AGENT_KV_LIMITER_FAIL_OPEN", True):
        assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is True
        assert rl.check_key_rate("key1") is True


@mock.patch.object(rl, "_redis", side_effect=OSError("redis down"))
def test_limiter_unavailability_is_logged_at_error_level(m_redis, caplog):
    """`logger.exception`, not `logger.warning`. The old level is part of why
    this sat unnoticed -- a limiter being gone is an error, not a warning.
    """
    with mock.patch.object(settings, "AGENT_KV_LIMITER_FAIL_OPEN", False):
        with caplog.at_level("ERROR", logger=rl.logger.name):
            rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1")
            rl.check_key_rate("key1")
    assert [r.levelname for r in caplog.records] == ["ERROR", "ERROR"]
    # The traceback is attached, so the actual Redis failure is diagnosable.
    assert all(r.exc_info for r in caplog.records)


@mock.patch.object(rl, "_redis", side_effect=OSError("redis down"))
def test_release_still_tolerates_an_unreachable_backend(m_redis):
    """Release must stay best-effort regardless: it is called on terminal
    paths (finalize, cancel, sweep) where raising would abort the caller's own
    work, and a slot it cannot free expires on its own TTL.
    """
    rl.AgentKVConcurrencyLimiter.release("org1", "job1")


# ---------------------------------------------------------------------------
# The published env table said both limiters "fail open on Redis errors", for
# the whole life of the branch that made them fail CLOSED. An operator reading
# it would size a Redis outage as "requests get through" when the real
# behaviour is "every submit 429s" -- the opposite incident. Docs are the
# contract for a public API, so this is pinned rather than trusted.
# ---------------------------------------------------------------------------

_DOCS = pathlib.Path(__file__).resolve().parents[3] / "docs" / "agent-kv-api.md"


@pytest.mark.parametrize(
    "variable",
    ["AGENT_KV_CONCURRENT_LIMIT", "AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE"],
)
def test_the_docs_do_not_describe_either_limiter_as_failing_open(variable):
    row = next(line for line in _DOCS.read_text().splitlines() if f"`{variable}`" in line)
    assert "fails open" not in row.casefold(), row
    assert "closed" in row.casefold(), (
        f"the {variable} row must say what a Redis outage does, and it fails "
        "closed -- see _limiter_failure_allows_request"
    )


def test_the_waiver_flag_is_documented_with_its_real_default():
    text = _DOCS.read_text()
    assert "`AGENT_KV_LIMITER_FAIL_OPEN`" in text, (
        "the only way to restore fail-open is undocumented, so the only "
        "documented behaviour was the wrong one"
    )
    assert not rl._limiter_failure_allows_request() or getattr(
        settings, "AGENT_KV_LIMITER_FAIL_OPEN", False
    ), "the default must be fail-closed"
