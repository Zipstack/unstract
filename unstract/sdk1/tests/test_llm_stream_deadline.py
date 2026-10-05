"""``LLM.complete()`` caps a streamed completion at ``LLM_STREAM_MAX_SECONDS``.

In production (UN-4223) single ``vertex_ai/gemini-3.1-flash-lite`` calls kept
streaming for 2+ hours: no timeout fired, memory climbed to ~10 GB, and pod
liveness eventually took whole executor pods offline. A read timeout resets on
every chunk, so only a total wall-clock limit stops a model stuck generating.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from importlib import import_module
from itertools import cycle
from typing import TYPE_CHECKING
from unittest.mock import patch

import litellm
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

ANTHROPIC_ADAPTER_ID = "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"
_REAL_COMPLETION = litellm.completion


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    import sys
    from types import ModuleType

    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


@pytest.fixture
def no_cost() -> Iterator[None]:
    llm_module = _load_llm_module()
    with patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)):
        yield


def _content_chunks() -> list[object]:
    """Real litellm stream chunks that carry text, produced without network."""
    chunks = list(
        _REAL_COMPLETION(
            model="anthropic/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
            mock_response="loop ",
            api_key="test-key",
        )
    )
    return [c for c in chunks if c["choices"] and c["choices"][0].delta.content]


def test_endless_stream_fails_at_the_limit(
    no_cost: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm_module = _load_llm_module()
    llm = llm_module.LLM(
        adapter_id=ANTHROPIC_ADAPTER_ID,
        adapter_metadata={
            "model": "claude-sonnet-4-6",
            "api_key": "test-key",
            "max_retries": 2,
        },
    )
    chunks = _content_chunks()
    calls: list[int] = []

    def endless(**_: object) -> Iterator[object]:
        calls.append(1)
        for chunk in cycle(chunks):
            time.sleep(0.005)
            yield chunk

    monkeypatch.setenv("LLM_STREAM_MAX_SECONDS", "0.05")
    with (
        patch.object(llm_module.litellm, "completion", endless),
        pytest.raises(
            llm_module.LLMError, match="exceeded its 0.05s total time limit"
        ) as exc,
    ):
        llm.complete("hi")

    assert len(calls) == 1  # a runaway generation is never replayed
    # The adapter is named once, by LLM's wrapper.
    assert str(exc.value).startswith("Error from LLM adapter 'anthropic': stream")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 1800.0),
        ("", 1800.0),
        ("600", 600.0),
        (" 900.5 ", 900.5),
        ("0", None),
        ("-5", None),
    ],
)
def test_limit_is_read_from_the_environment(
    raw: str | None, expected: float | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm_module = _load_llm_module()
    if raw is None:
        monkeypatch.delenv("LLM_STREAM_MAX_SECONDS", raising=False)
    else:
        monkeypatch.setenv("LLM_STREAM_MAX_SECONDS", raw)

    assert llm_module._stream_max_seconds() == expected


@pytest.mark.parametrize("raw", ["30m", "inf", "-inf", "nan"])
def test_invalid_limit_falls_back_to_the_default_with_a_warning(
    raw: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A typo, or a non-finite value ``float()`` accepts, keeps the limit on."""
    llm_module = _load_llm_module()
    monkeypatch.setenv("LLM_STREAM_MAX_SECONDS", raw)

    with caplog.at_level(logging.WARNING, logger=llm_module.logger.name):
        assert llm_module._stream_max_seconds() == 1800.0

    assert f"LLM_STREAM_MAX_SECONDS={raw!r} is not a finite number" in caplog.text
