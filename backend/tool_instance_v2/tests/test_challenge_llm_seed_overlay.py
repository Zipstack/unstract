"""Regression tests for seeding a tool instance's ``challenge_llm`` from the
exported tool's resolved settings.

The deploy-time failure this closes: a tool exported with LLMChallenge *enabled*
still ended in pipeline status ERROR with
``422 Unprocessable Entity: Tool validation failed``.

The chain:

  1. Export resolves a real ``challenge_llm`` (falling back to the default
     profile's LLM) and stores it under ``tool_metadata[tool_settings]``.
  2. Tool-instance creation seeds metadata from ``get_default_settings``, which
     walks the *spec*: a ``"type": "string"`` property with no ``default`` is
     seeded ``""``. ``challenge_llm`` has no spec default, so the instance
     stores ``""`` -- throwing away the value export already resolved.
  3. Because ``challenge_llm`` declares ``adapterType: "LLM"``,
     ``_update_schema_for_adapter_type`` injects ``enum: [<real adapter ids>]``.
  4. Validation rejects ``""`` (an enum violation), regardless of the sibling
     PR's ``frame_spec`` change -- that change only spares the challenge-*off*
     case by omitting the enum; with challenge *on*, the enum is present and the
     seeded ``""`` still fails.

The fix overlays the resolved settings onto the spec-seeded defaults, for
spec-declared keys only, so ``challenge_llm`` carries its real adapter id.

These tests exercise the real overlay logic and the real enum-injection body
composed together -- a value seeded by the overlay must validate against the
schema a challenge-enabled instance is checked against. Django is not importable
in a plain checkout (no ``pytest-django``), so the relevant function bodies are
executed against stubs, mirroring
``prompt_studio_core_v2/tests/test_build_index_payload.py``. If a function is
renamed the tests fail rather than silently skip.
"""

from __future__ import annotations

import enum
import importlib.util
import re
import sys
import textwrap
import types
from pathlib import Path
from typing import Any

import pytest

jsonschema = pytest.importorskip(
    "jsonschema", reason="jsonschema is required to exercise the real validator"
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
TOOL_PROCESSOR = BACKEND_DIR / "tool_instance_v2" / "tool_processor.py"
SERIALIZERS = BACKEND_DIR / "tool_instance_v2" / "serializers.py"
DTO_PATH = REPO_ROOT / "unstract" / "tool-registry" / "src" / "unstract" / "tool_registry"

REAL_ADAPTER_ID = "11111111-2222-3333-4444-555555555555"


class _AdapterTypes(str, enum.Enum):
    LLM = "LLM"
    EMBEDDING = "EMBEDDING"
    VECTOR_DB = "VECTOR_DB"
    X2TEXT = "X2TEXT"
    OCR = "OCR"


def _stub_package(name: str, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = []  # type: ignore[attr-defined]
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_spec_class() -> Any:
    _stub_package("unstract")
    _stub_package("unstract.sdk1")
    _stub_package("unstract.sdk1.constants", AdapterTypes=_AdapterTypes)
    _stub_package("unstract.tool_registry")
    constants_spec = importlib.util.spec_from_file_location(
        "unstract.tool_registry.constants", DTO_PATH / "constants.py"
    )
    constants = importlib.util.module_from_spec(constants_spec)
    constants_spec.loader.exec_module(constants)
    sys.modules["unstract.tool_registry.constants"] = constants
    dto_spec = importlib.util.spec_from_file_location(
        "unstract.tool_registry.dto", DTO_PATH / "dto.py"
    )
    dto = importlib.util.module_from_spec(dto_spec)
    dto_spec.loader.exec_module(dto)
    return dto.Spec


SPEC_CLS = _load_spec_class()


def _extract(path: Path, start_marker: str) -> str:
    source = path.read_text()
    if start_marker not in source:
        pytest.fail(
            f"Could not find {start_marker!r} in {path}. If it was renamed, "
            "update this test rather than deleting it."
        )
    body = source[source.index(start_marker) :]
    end = body.find("\n    @staticmethod")
    if end != -1:
        body = body[:end]
    return textwrap.dedent(body)


def _real_update_schema():
    body = _extract(TOOL_PROCESSOR, "    def _update_schema_for_adapter_type(")
    body = re.sub(
        r"def _update_schema_for_adapter_type\([^)]*\)[^:]*:",
        "def update_schema(schema, keys, adapter_type, user):",
        body,
        flags=re.S,
    )

    class _Adapter:
        def __init__(self, adapter_id: str, name: str) -> None:
            self.id = adapter_id
            self.adapter_name = name

    class _AdapterProcessor:
        @staticmethod
        def get_adapters_by_type(adapter_type: Any, user: Any = None) -> list[_Adapter]:
            return [_Adapter(REAL_ADAPTER_ID, "My LLM")]

    namespace: dict[str, Any] = {
        "AdapterProcessor": _AdapterProcessor,
        "Spec": SPEC_CLS,
        "AdapterTypes": _AdapterTypes,
        "User": object,
        "Any": Any,
    }
    exec(compile(body, str(TOOL_PROCESSOR), "exec"), namespace)
    return namespace["update_schema"]


def _extract_overlay_snippet() -> str:
    """Return the real overlay loop from ``create``, as an executable snippet.

    Extracting the exact shipped lines (rather than reimplementing them) is what
    makes the behavioural tests below fail when the real loop is broken -- a
    reimplemented copy would stay green through a production regression.

    The loop is bracketed by two stable anchors in the serializer source. If the
    anchors move, extraction fails loudly here instead of silently testing a
    copy.
    """
    source = SERIALIZERS.read_text()
    start = "        for key in tool_settings:"
    end = "        validated_data[TIKey.METADATA] = {"
    if start not in source or end not in source:
        pytest.fail(
            "Could not locate the overlay loop in serializers.py by its anchors. "
            "If create() was restructured, re-derive this test rather than "
            "deleting it."
        )
    block = source[source.index(start) : source.index(end)]
    return textwrap.dedent(block)


_OVERLAY_SNIPPET = _extract_overlay_snippet()


def _overlay(spec_defaults: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    """Run the REAL overlay loop extracted from the serializer.

    Binds ``tool_settings`` and ``resolved_settings`` the way ``create`` does,
    executes the shipped loop verbatim, and returns the mutated settings. So a
    change that breaks the real loop breaks these tests.
    """
    namespace: dict[str, Any] = {
        "tool_settings": dict(spec_defaults),
        "resolved_settings": resolved,
    }
    exec(compile(_OVERLAY_SNIPPET, str(SERIALIZERS), "exec"), namespace)
    return namespace["tool_settings"]


def _instance_schema(*, enable_challenge: bool) -> dict[str, Any]:
    """Build the schema a challenge-(on|off) instance is validated against.

    Mirrors the enum injection ``get_json_schema_for_tool`` applies. The
    ``adapterType``/``required`` handling matches the sibling ``frame_spec``
    fix: with challenge off the property is a plain string, with it on the
    adapter enum is injected and the value is required.
    """
    challenge_prop: dict[str, Any] = {
        "type": "string",
        "title": "Challenger LLM",
        "description": "LLM to use for LLMChallenge",
    }
    required: list[str] = []
    if enable_challenge:
        challenge_prop["adapterType"] = "LLM"
        required = ["challenge_llm"]
    else:
        challenge_prop["default"] = ""

    spec = SPEC_CLS(
        title="tool",
        description="An exported Prompt Studio tool",
        required=required,
        properties={"challenge_llm": challenge_prop},
    )
    update_schema = _real_update_schema()
    update_schema(spec, spec.get_llm_adapter_properties_keys(), _AdapterTypes.LLM, None)
    return spec.to_dict()


def _errors(schema: dict[str, Any], instance: dict[str, Any]) -> list[Any]:
    return list(jsonschema.Draft7Validator(schema).iter_errors(instance))


class TestChallengeEnabledSeed:
    """The bug: a challenge-enabled tool must deploy with its resolved LLM."""

    def test_resolved_value_is_seeded_over_the_empty_default(self) -> None:
        spec_seeded = {"challenge_llm": ""}  # what get_default_settings produces
        resolved = {"challenge_llm": REAL_ADAPTER_ID}  # what export resolved

        seeded = _overlay(spec_seeded, resolved)

        assert seeded["challenge_llm"] == REAL_ADAPTER_ID

    def test_seeded_instance_passes_deploy_validation(self) -> None:
        """End-to-end: the overlaid value validates against the enum schema."""
        seeded = _overlay({"challenge_llm": ""}, {"challenge_llm": REAL_ADAPTER_ID})
        schema = _instance_schema(enable_challenge=True)

        assert _errors(schema, {"challenge_llm": seeded["challenge_llm"]}) == []

    def test_pre_fix_empty_seed_still_fails(self) -> None:
        """Characterise the pre-fix behaviour to prove the test discriminates.

        Without the overlay the instance keeps ``""`` and the enum rejects it.
        """
        schema = _instance_schema(enable_challenge=True)

        errors = _errors(schema, {"challenge_llm": ""})

        assert errors, "The pre-fix empty value must still fail; else the test is inert"
        assert any(e.validator == "enum" for e in errors)


def test_overlay_ignores_keys_the_spec_does_not_declare() -> None:
    """The export's settings are a superset; only spec keys may be overlaid.

    ``tool_settings`` from ``frame_export_json`` carries ``llm``, ``vector-db``,
    ``preamble``, ... None of these belong in the instance metadata, so the
    overlay must not import them just because export resolved them.
    """
    spec_seeded = {"challenge_llm": "", "enable_highlight": False}
    resolved = {
        "challenge_llm": REAL_ADAPTER_ID,
        "llm": "some-llm-id",
        "vector-db": "some-vector-id",
        "preamble": "leaked preamble",
    }

    seeded = _overlay(spec_seeded, resolved)

    assert set(seeded) == {"challenge_llm", "enable_highlight"}
    assert "llm" not in seeded
    assert "vector-db" not in seeded
    assert "preamble" not in seeded


def test_overlay_is_a_noop_without_resolved_settings() -> None:
    """Non-Prompt-Studio tools resolve to {}; the seed must be untouched.

    ``get_resolved_settings`` returns {} for a missing registry row, so a
    regular registry tool (or agentic tool) keeps exactly its spec defaults.
    """
    spec_seeded = {"challenge_llm": "", "enable_highlight": False}

    seeded = _overlay(spec_seeded, {})

    assert seeded == spec_seeded


def test_get_resolved_settings_reads_the_tool_settings_block() -> None:
    """The helper must dig into ``tool_metadata[tool_settings]``, not the top level.

    Exercises the real ``get_resolved_settings`` body against a stubbed ORM, so
    a wrong key path (reading ``tool_metadata`` directly) is caught.
    """
    helper_path = (
        BACKEND_DIR
        / "prompt_studio"
        / "prompt_studio_registry_v2"
        / "prompt_studio_registry_helper.py"
    )
    body = _extract(helper_path, "    def get_resolved_settings(prompt_registry_id: str)")
    body = body.replace(
        "def get_resolved_settings(prompt_registry_id: str) -> dict[str, Any]:",
        "def get_resolved_settings(prompt_registry_id):",
    )

    constants_spec = importlib.util.spec_from_file_location(
        "_psr_constants_overlay",
        BACKEND_DIR / "prompt_studio" / "prompt_studio_registry_v2" / "constants.py",
    )
    constants = importlib.util.module_from_spec(constants_spec)
    constants_spec.loader.exec_module(constants)

    class _Row:
        def __init__(self, metadata: dict[str, Any]) -> None:
            self.tool_metadata = metadata

    class _Manager:
        def __init__(self, row: _Row | None) -> None:
            self._row = row

        def get(self, pk: str) -> _Row:
            if self._row is None:
                raise LookupError("no such row")
            return self._row

    class _Logger:
        @staticmethod
        def warning(*args: Any, **kwargs: Any) -> None:
            return None

    def _make(row: _Row | None):
        registry = type("PromptStudioRegistry", (), {"objects": _Manager(row)})
        namespace: dict[str, Any] = {
            "PromptStudioRegistry": registry,
            "JsonSchemaKey": constants.JsonSchemaKey,
            "logger": _Logger,
            "Any": Any,
        }
        exec(compile(body, str(helper_path), "exec"), namespace)
        return namespace["get_resolved_settings"]

    tool_settings = {"challenge_llm": REAL_ADAPTER_ID}
    fetch = _make(_Row({"tool_settings": tool_settings}))
    assert fetch("some-id") == tool_settings

    # Missing row -> {} (the no-op path relied on by the serializer).
    fetch_missing = _make(None)
    assert fetch_missing("absent") == {}

    # Row with no settings block -> {}.
    fetch_empty = _make(_Row({}))
    assert fetch_empty("some-id") == {}
