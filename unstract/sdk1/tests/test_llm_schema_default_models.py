"""Form defaults for the model field must name models the providers still serve.

A user who accepts the prefilled model gets a failed request when the default
has been retired, so retired ids must not come back as defaults.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

STATIC_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "unstract"
    / "sdk1"
    / "adapters"
    / "llm1"
    / "static"
)

RETIRED_DEFAULT_MODELS = {
    "openai.json": {"gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "o1", "o3-mini", "o4-mini"},
    "gemini.json": {"gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash"},
    "anthropic.json": {"claude-instant-1.2", "claude-2.1", "claude-3-opus-20240229"},
}


@pytest.mark.parametrize("schema_name", sorted(RETIRED_DEFAULT_MODELS))
def test_model_default_is_not_retired(schema_name: str) -> None:
    props = json.loads((STATIC_DIR / schema_name).read_text())["properties"]
    default = props["model"]["default"]
    assert default, f"{schema_name} has no model default"
    assert default not in RETIRED_DEFAULT_MODELS[schema_name]
