"""The UNSTRACT_LLM_MOCK_RESPONSE escape hatch and the litellm mock contract.

Hermetic execute-path coverage rests on both, so pin them here: a litellm bump
that broke either would otherwise surface far from its cause.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module

import litellm
import pytest


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    import sys
    from types import ModuleType

    # Stub python-magic for the import only, so we neither depend on libmagic
    # nor leave a stub shadowing a real `magic` for the rest of the process.
    inserted = "magic" not in sys.modules
    if inserted:
        sys.modules["magic"] = ModuleType("magic")
    try:
        return import_module("unstract.sdk1.llm")
    finally:
        if inserted:
            del sys.modules["magic"]


def _inject(kwargs: dict[str, object]) -> dict[str, object]:
    _load_llm_module()._inject_mock_response(kwargs)
    return kwargs


@pytest.fixture(autouse=True)
def _reset_warn_cache() -> None:
    _load_llm_module()._warn_mock_active.cache_clear()
    _load_llm_module()._warn_mock_refused.cache_clear()


@pytest.fixture(autouse=True)
def _allowed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hatch needs a permitted ENVIRONMENT; the guard itself is tested below."""
    monkeypatch.setenv("ENVIRONMENT", "test")


def test_inject_is_noop_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNSTRACT_LLM_MOCK_RESPONSE", raising=False)
    assert _inject({"model": "gpt-4o"}) == {"model": "gpt-4o"}


def test_inject_is_noop_when_env_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # The overlay exports `UNSTRACT_LLM_MOCK_RESPONSE=` (empty) into workers when
    # the var is unset upstream; that empty string must stay a no-op, or every
    # local stack run would silently mock completions.
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "")
    assert _inject({"model": "gpt-4o"}) == {"model": "gpt-4o"}


def test_inject_sets_mock_response_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "canned answer")
    assert _inject({"model": "gpt-4o"})["mock_response"] == "canned answer"


@pytest.mark.parametrize("environment", ["production", "staging", "", "  "])
def test_mock_refused_outside_allowed_environments(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    # The whole point of the guard: a stray mock var in a real deployment must
    # not fake completions and their billing.
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "canned")
    monkeypatch.setenv("ENVIRONMENT", environment)
    assert _inject({"model": "gpt-4o"}) == {"model": "gpt-4o"}


def test_mock_refused_when_environment_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    # Production k8s sets no ENVIRONMENT at all, so unset must fail closed.
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "canned")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert _inject({"model": "gpt-4o"}) == {"model": "gpt-4o"}


def test_refusal_is_warned_so_a_real_bill_is_never_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "canned")
    monkeypatch.setenv("ENVIRONMENT", "production")
    with caplog.at_level("WARNING", logger="unstract.sdk1.llm"):
        _inject({"model": "gpt-4o"})
    assert any("not one of" in r.message for r in caplog.records), caplog.text


@pytest.mark.parametrize("environment", ["test", "development", "TEST", " Development "])
def test_mock_applies_in_allowed_environments(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    # `development` is what base compose sets on the workers that run the
    # injection; a guard that only accepted `test` would kill the local stack.
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "canned")
    monkeypatch.setenv("ENVIRONMENT", environment)
    assert _inject({"model": "gpt-4o"})["mock_response"] == "canned"


def test_inject_does_not_clobber_explicit_mock_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "from-env")
    assert _inject({"mock_response": "explicit"})["mock_response"] == "explicit"


def test_inject_warns_once_while_active(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "from-env")
    with caplog.at_level("WARNING", logger="unstract.sdk1.llm"):
        _inject({"model": "gpt-4o"})
        _inject({"model": "gpt-4o"})
    warnings = [r for r in caplog.records if "UNSTRACT_LLM_MOCK_RESPONSE" in r.message]
    # Once per process, not once per completion: a worker would flood otherwise.
    assert len(warnings) == 1, caplog.text


def test_inject_does_not_warn_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("UNSTRACT_LLM_MOCK_RESPONSE", raising=False)
    with caplog.at_level("WARNING", logger="unstract.sdk1.llm"):
        _inject({"model": "gpt-4o"})
    assert not caplog.records, caplog.text


def test_every_completion_path_injects_the_mock() -> None:
    # The hook is worthless if a completion method doesn't call it; deleting any
    # call site would otherwise leave this suite green and only surface as an
    # opaque "no API key" worker failure in the e2e tier.
    import inspect

    llm = _load_llm_module()
    for name in ("complete", "complete_vision", "stream_complete", "acomplete"):
        src = inspect.getsource(getattr(llm.LLM, name))
        assert "_inject_mock_response(completion_kwargs)" in src, name


def test_litellm_mock_contract_returns_string_and_fixed_usage() -> None:
    # 10/20/30 are litellm's defaults, asserted verbatim by the e2e tests.
    resp = litellm.completion(
        model="gpt-4o",
        messages=[{"role": "user", "content": "anything"}],
        mock_response="canned answer",
    )
    assert resp["choices"][0]["message"]["content"] == "canned answer"
    assert resp["usage"]["prompt_tokens"] == 10
    assert resp["usage"]["completion_tokens"] == 20
    assert resp["usage"]["total_tokens"] == 30


def test_litellm_mock_error_sentinel_raises() -> None:
    # Error paths need the sentinel to raise rather than complete normally.
    with pytest.raises(litellm.RateLimitError):
        litellm.completion(
            model="gpt-4o",
            messages=[{"role": "user", "content": "anything"}],
            mock_response="litellm.RateLimitError",
        )
