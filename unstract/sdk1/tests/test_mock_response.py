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

    # Stub python-magic so importing LLM does not depend on libmagic.
    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


def _inject(kwargs: dict[str, object]) -> dict[str, object]:
    _load_llm_module()._inject_mock_response(kwargs)
    return kwargs


def test_inject_is_noop_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNSTRACT_LLM_MOCK_RESPONSE", raising=False)
    assert _inject({"model": "gpt-4o"}) == {"model": "gpt-4o"}


def test_inject_sets_mock_response_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "canned answer")
    assert _inject({"model": "gpt-4o"})["mock_response"] == "canned answer"


def test_inject_does_not_clobber_explicit_mock_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNSTRACT_LLM_MOCK_RESPONSE", "from-env")
    assert _inject({"mock_response": "explicit"})["mock_response"] == "explicit"


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
