"""Tests for the ``get_barrier()`` factory + ``WORKER_BARRIER_BACKEND`` flag.

Phase 6b selects the ``Barrier`` substrate at runtime via an env flag.
This test suite pins:

- Default (env unset) → ``CeleryChordBarrier`` — protects against any
  production behaviour change at merge time; downstream envs that
  haven't added the new flag still run the same substrate they ran
  yesterday.
- ``WORKER_BARRIER_BACKEND=chord`` → ``CeleryChordBarrier``.
- ``WORKER_BARRIER_BACKEND=redis`` → ``RedisDecrBarrier``.
- Unknown values raise ``ValueError`` — silent fallback to default
  would mask a typo'd flag in production env, which the canary
  must not allow.
- Case + whitespace tolerance — operators frequently set env vars
  via shell scripts or k8s configmaps; ``"  REDIS  "`` should
  resolve the same as ``"redis"``.
- ``BarrierBackend`` enum membership — the canonical string values
  match what operators set in env.
"""

from __future__ import annotations

import pytest

from queue_backend import (
    BarrierBackend,
    CeleryChordBarrier,
    RedisDecrBarrier,
    get_barrier,
)


class TestBarrierBackendEnum:
    def test_chord_value_is_canonical_string(self):
        """The enum value is what operators set in env. If this
        drifts, the factory's dispatch breaks silently for one
        substrate (the one whose enum value no longer matches the
        documented env value)."""
        assert BarrierBackend.CHORD.value == "chord"
        assert BarrierBackend.REDIS.value == "redis"

    def test_str_enum_string_equality(self):
        """``StrEnum`` members compare equal to their string values —
        means tests + production code can use either form
        interchangeably without conversion."""
        assert BarrierBackend.CHORD == "chord"
        assert BarrierBackend.REDIS == "redis"


class TestGetBarrierFactory:
    def test_default_returns_celery_chord_barrier(self, monkeypatch):
        """Env unset → ``CeleryChordBarrier``. This is what protects
        production from a behaviour change at merge time — downstream
        envs (``unstract-cloud``, self-hosted, etc.) that haven't
        added the new flag run the same substrate they ran yesterday."""
        monkeypatch.delenv("WORKER_BARRIER_BACKEND", raising=False)
        barrier = get_barrier()
        assert isinstance(barrier, CeleryChordBarrier)

    def test_chord_selects_celery_chord_barrier(self, monkeypatch):
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", BarrierBackend.CHORD)
        assert isinstance(get_barrier(), CeleryChordBarrier)

    def test_redis_selects_redis_decr_barrier(self, monkeypatch):
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", BarrierBackend.REDIS)
        assert isinstance(get_barrier(), RedisDecrBarrier)

    def test_unknown_value_raises_loudly(self, monkeypatch):
        """Silent fallback to default would mask a typo'd production
        env (``rediz``, ``REDDIS``, ``redis-decr``) — the canary
        must surface the misconfiguration."""
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", "rediz")
        with pytest.raises(ValueError, match=r"rediz"):
            get_barrier()

    def test_empty_string_raises_loudly(self, monkeypatch):
        """Empty string is not the same as "unset" — it's a positive
        misconfiguration (e.g. an unsubstituted ``$BARRIER`` in a
        shell script). Surface it rather than falling back to
        default, which would mask the bug."""
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", "")
        with pytest.raises(ValueError):
            get_barrier()

    def test_case_insensitive(self, monkeypatch):
        """Operators frequently set env vars via shell heredocs or
        k8s configmaps with inconsistent casing. ``REDIS`` and
        ``Redis`` should resolve the same as ``redis``."""
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", "REDIS")
        assert isinstance(get_barrier(), RedisDecrBarrier)
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", "Chord")
        assert isinstance(get_barrier(), CeleryChordBarrier)

    def test_whitespace_tolerated(self, monkeypatch):
        """Stray whitespace (common from shell substitutions) is
        stripped before the membership check."""
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", "  redis  ")
        assert isinstance(get_barrier(), RedisDecrBarrier)

    def test_returns_fresh_instance_per_call(self, monkeypatch):
        """``get_barrier()`` builds a new instance each call rather
        than returning a singleton. Call sites that want a singleton
        (e.g. ``orchestration_utils._BARRIER``) cache it at module
        load time. Tests can flip the env per-test without leaking
        a stale instance from a previous test."""
        monkeypatch.setenv("WORKER_BARRIER_BACKEND", "chord")
        a = get_barrier()
        b = get_barrier()
        assert a is not b
        assert isinstance(a, CeleryChordBarrier)
        assert isinstance(b, CeleryChordBarrier)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
