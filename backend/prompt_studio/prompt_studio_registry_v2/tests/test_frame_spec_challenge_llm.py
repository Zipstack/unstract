"""Regression tests for ``PromptStudioRegistryHelper.frame_spec``'s handling of
``challenge_llm``.

Pins the fix for the deploy-time failure where an exported tool that never used
LLMChallenge ended in pipeline status ERROR with
``422 Unprocessable Entity: Tool validation failed``.

The mechanism these tests lock down:

  1. ``get_default_settings`` seeds a ``"type": "string"`` property that has no
     spec ``default`` with ``""``, so the tool instance stores
     ``challenge_llm: ""``.
  2. A property declaring ``adapterType: "LLM"`` gets an ``enum`` of real
     adapter IDs injected by ``_update_schema_for_adapter_type``.
  3. ``""`` is not in that enum, so validation rejects it -- and this fired
     regardless of ``enable_challenge``.

Note the failure is an **enum** violation, not a ``required`` one: a
present-but-empty key satisfies ``required``. Dropping ``challenge_llm`` from
``required`` alone therefore does *not* fix it, which is why ``frame_spec``
makes the ``adapterType`` declaration itself conditional. These tests assert
that distinction directly so a future "simplification" back to an unconditional
``adapterType`` fails loudly.

The tests exercise the **real** ``frame_spec`` body and the **real**
``_update_schema_for_adapter_type`` body composed together, rather than
reimplementing either -- a copy of the logic would stay green even if the
shipped code broke.

Django is not importable in a plain checkout (no ``pytest-django``; the app
registry is not loaded), and both helpers live in Django-coupled modules. So
the two function bodies are extracted from source and executed against stubs,
mirroring the approach in
``prompt_studio_core_v2/tests/test_build_index_payload.py``. If either function
cannot be extracted -- because it was renamed or restructured -- the tests fail
rather than silently skip.
"""

from __future__ import annotations

import enum
import importlib.util
import re
import sys
import textwrap
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

jsonschema = pytest.importorskip(
    "jsonschema", reason="jsonschema is required to exercise the real validator"
)

BACKEND_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_DIR.parent

REGISTRY_HELPER = (
    BACKEND_DIR
    / "prompt_studio"
    / "prompt_studio_registry_v2"
    / "prompt_studio_registry_helper.py"
)
TOOL_PROCESSOR = BACKEND_DIR / "tool_instance_v2" / "tool_processor.py"
DTO_PATH = REPO_ROOT / "unstract" / "tool-registry" / "src" / "unstract" / "tool_registry"


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
    """Load the real ``Spec`` dataclass without importing the SDK-heavy package."""
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


def _extract_function(path: Path, start_marker: str) -> str:
    """Return the dedented source of a method beginning with ``start_marker``.

    Fails the test if the marker is absent, so a rename surfaces here instead of
    quietly reducing coverage.
    """
    source = path.read_text()
    if start_marker not in source:
        pytest.fail(
            f"Could not find {start_marker!r} in {path}. If it was renamed or "
            "restructured, update this test rather than deleting it."
        )
    body = source[source.index(start_marker) :]
    end = body.find("\n    @staticmethod")
    if end != -1:
        body = body[:end]
    return textwrap.dedent(body)


SPEC_CLS = _load_spec_class()


def _load_json_schema_key() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_psr_constants",
        BACKEND_DIR / "prompt_studio" / "prompt_studio_registry_v2" / "constants.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.JsonSchemaKey


def _real_frame_spec():
    body = _extract_function(
        REGISTRY_HELPER, "    def frame_spec(tool: CustomTool) -> Spec:"
    )
    body = body.replace(
        "def frame_spec(tool: CustomTool) -> Spec:", "def frame_spec(tool):"
    )
    namespace: dict[str, Any] = {
        "Spec": SPEC_CLS,
        "Any": Any,
        "JsonSchemaKey": _load_json_schema_key(),
    }
    exec(compile(body, str(REGISTRY_HELPER), "exec"), namespace)
    return namespace["frame_spec"]


def _real_update_schema():
    """Extract ``_update_schema_for_adapter_type`` with a stubbed adapter lookup."""
    body = _extract_function(TOOL_PROCESSOR, "    def _update_schema_for_adapter_type(")
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


REAL_ADAPTER_ID = "11111111-2222-3333-4444-555555555555"


@dataclass
class _FakeCustomTool:
    """Minimal stand-in for ``CustomTool`` -- ``frame_spec`` reads only these."""

    tool_id: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    description: str = "A tool exported from Prompt Studio"
    enable_challenge: bool = False


def _build_instance_schema(*, enable_challenge: bool) -> dict[str, Any]:
    """Compose export-time ``frame_spec`` with deploy-time enum injection.

    This is the exact path a tool instance's metadata is validated against:
    ``frame_spec`` output is persisted as ``tool_spec`` and later rehydrated via
    ``Spec.from_dict`` in ``get_tool_by_prompt_registry_id``.
    """
    frame_spec = _real_frame_spec()
    update_schema = _real_update_schema()

    spec = frame_spec(_FakeCustomTool(enable_challenge=enable_challenge))
    llm_keys = spec.get_llm_adapter_properties_keys()
    update_schema(spec, llm_keys, _AdapterTypes.LLM, None)
    return spec.to_dict()


def _validation_errors(schema: dict[str, Any], instance: dict[str, Any]) -> list[Any]:
    return list(jsonschema.Draft7Validator(schema).iter_errors(instance))


def _seeded_default(schema: dict[str, Any], prop: str) -> Any:
    """Mimic ``ToolUtils.get_default_settings`` for a single property.

    Kept in lockstep with the real seeding rule: use the spec ``default`` when
    present, else the zero value for the declared type.
    """
    prop_schema = schema["properties"][prop]
    if "default" in prop_schema:
        return prop_schema["default"]
    return {"string": "", "integer": 0, "boolean": False}[prop_schema["type"]]


class TestChallengeDisabled:
    """With LLMChallenge off, an unset ``challenge_llm`` must deploy cleanly."""

    def test_seeded_empty_value_validates(self) -> None:
        """The reported bug: a tool that never used LLMChallenge 422s on deploy."""
        schema = _build_instance_schema(enable_challenge=False)
        seeded = _seeded_default(schema, "challenge_llm")

        errors = _validation_errors(schema, {"challenge_llm": seeded})

        assert errors == [], (
            "An instance seeded by get_default_settings must validate when "
            f"LLMChallenge is off; got {[e.validator for e in errors]}"
        )

    def test_no_enum_is_injected(self) -> None:
        """No ``adapterType`` means no enum, which is what makes "unset" legal.

        Guards the actual fix: dropping ``required`` alone would leave the enum
        in place and the 422 intact.
        """
        schema = _build_instance_schema(enable_challenge=False)

        assert "enum" not in schema["properties"]["challenge_llm"], (
            "challenge_llm must not carry an adapter enum while LLMChallenge is "
            "off, otherwise the empty seeded value is unrepresentable"
        )

    def test_challenge_llm_is_not_required(self) -> None:
        schema = _build_instance_schema(enable_challenge=False)
        assert "challenge_llm" not in schema.get("required", [])

    def test_a_real_adapter_id_still_validates(self) -> None:
        """Turning the feature off must not reject a value the user did set."""
        schema = _build_instance_schema(enable_challenge=False)
        assert _validation_errors(schema, {"challenge_llm": REAL_ADAPTER_ID}) == []


class TestChallengeEnabled:
    """With LLMChallenge on, the adapter constraint must still be enforced."""

    def test_empty_value_is_rejected(self) -> None:
        """The fix must not open a hole: challenge on + no LLM must not pass.

        This is the regression that a careless "just allow empty strings"
        implementation would introduce.
        """
        schema = _build_instance_schema(enable_challenge=True)

        errors = _validation_errors(schema, {"challenge_llm": ""})

        assert errors, "An enabled LLMChallenge must not accept an empty adapter"
        assert any(
            error.validator == "enum" for error in errors
        ), f"Expected an enum violation, got {[e.validator for e in errors]}"

    def test_missing_key_is_rejected(self) -> None:
        schema = _build_instance_schema(enable_challenge=True)
        errors = _validation_errors(schema, {})
        assert any(error.validator == "required" for error in errors)

    def test_real_adapter_id_validates(self) -> None:
        schema = _build_instance_schema(enable_challenge=True)
        assert _validation_errors(schema, {"challenge_llm": REAL_ADAPTER_ID}) == []

    def test_enum_holds_real_adapter_ids(self) -> None:
        schema = _build_instance_schema(enable_challenge=True)
        assert schema["properties"]["challenge_llm"]["enum"] == [REAL_ADAPTER_ID]


def test_other_adapter_properties_are_untouched() -> None:
    """The fix is scoped to ``challenge_llm``.

    ``_update_schema_for_adapter_type`` runs for LLM/EMBEDDING/VECTOR_DB/X2TEXT/
    OCR on every tool. Broadening the empty-value allowance there would make
    ``""`` valid for every optional adapter on every tool -- and then fail at
    runtime on ``AdapterInstance.objects.get(id="")``. This asserts the enum is
    injected verbatim for a property this fix does not own.
    """
    update_schema = _real_update_schema()
    spec = SPEC_CLS(
        title="unrelated-tool",
        description="A tool that is not from Prompt Studio",
        required=[],
        properties={"some_llm": {"type": "string", "adapterType": "LLM"}},
    )

    update_schema(spec, ["some_llm"], _AdapterTypes.LLM, None)

    assert spec.properties["some_llm"]["enum"] == [REAL_ADAPTER_ID], (
        "Adapter enums outside challenge_llm must keep listing only real " "adapter IDs"
    )
