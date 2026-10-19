"""Every LLM adapter form exposes the per-adapter ``enable_streaming`` switch.

The switch is read by ``LLM`` from the raw adapter metadata (see
``LLM._resolve_enable_streaming``). It defaults to on everywhere; the form
field exists so an endpoint that cannot stream can be opted out on its own
adapter.
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
SCHEMAS = sorted(STATIC_DIR.glob("*.json"))


def test_static_dir_has_schemas() -> None:
    assert len(SCHEMAS) >= 14


@pytest.mark.parametrize("schema_path", SCHEMAS, ids=[p.name for p in SCHEMAS])
def test_schema_exposes_enable_streaming(schema_path: Path) -> None:
    props = json.loads(schema_path.read_text())["properties"]
    field = props.get("enable_streaming")
    assert field is not None, f"{schema_path.name} lacks enable_streaming"
    assert field["type"] == "boolean"
    assert field["title"] == "Enable Streaming"
    assert field["default"] is True
