"""Regression tests for ``PromptStudioRegistryHelper.frame_spec``'s handling of
``challenge_llm``.

Pins the fix for the deploy-time failure where an exported tool ended in
pipeline status ERROR with ``422 Unprocessable Entity: Tool validation failed``.

The mechanism these tests lock down:

  1. ``ToolUtils.get_default_settings`` seeds each spec property into tool
     instance metadata using the spec ``default`` when present, else the zero
     value for the declared type -- ``""`` for a string.
  2. A property declaring ``adapterType: "LLM"`` gets an ``enum`` of real
     adapter IDs injected by ``_update_schema_for_adapter_type``.
  3. ``""`` is not in that enum, so deployment validation rejected it.

The fix seeds ``challenge_llm`` with a resolved adapter ID rather than dropping
its ``adapterType``. That distinction is load-bearing and is asserted directly
here: ``adapterType`` is the sole discriminator in ``Spec.get_adapter_properties``
(tool-registry ``dto.py``), so removing it would silently unregister
``challenge_llm`` from every adapter-aware path -- the ``challenge_llm_adapter_id``
write that runtime reads, the settings-form dropdown, and the lazy adapter-id
migration check. ``test_adapter_type_is_always_declared`` fails loudly if a
future change pops it again.

These tests exercise the real ``frame_spec`` and the real
``_update_schema_for_adapter_type``, patching only the two DB lookups (the
default profile and the adapter list). Nothing is stubbed into ``sys.modules``:
that pattern shadows the real ``unstract.*`` packages for every later test in the
pytest process and was deliberately removed from this repo (see ``9a76a745`` and
``b60dd6f3``).

Every real import happens inside ``_deps()`` rather than at module scope -- see
its docstring for why.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import jsonschema
import pytest


def _deps():
    """Import everything this module needs, at call time rather than import time.

    Nothing is imported at module scope on purpose. ``frame_spec`` and
    ``ToolProcessor`` are Django-coupled, and the ``unit-backend`` rig group
    runs without ``pytest-django`` and without ``DJANGO_SETTINGS_MODULE``, so a
    module-level import raises ``ImproperlyConfigured`` during collection and
    takes the whole file down.

    ``django`` genuinely missing is an environment gap -> skip. Anything else is
    a real problem and fails loudly: in particular, a sibling test module that
    stubs ``unstract.*`` or ``account_v2`` into ``sys.modules`` at its own import
    time (pytest imports every module during collection, before running any
    test) leaves these imports resolving to mocks. Skipping on that would hide
    the breakage instead of reporting it.
    """
    try:
        import django
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"django is not installed: {exc}")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
    django.setup()

    from tool_instance_v2.tool_processor import ToolProcessor
    from unstract.sdk1.constants import AdapterTypes
    from unstract.tool_registry.dto import Spec
    from unstract.tool_registry.tool_utils import ToolUtils

    from prompt_studio.prompt_studio_registry_v2.prompt_studio_registry_helper import (
        PromptStudioRegistryHelper,
    )

    return SimpleNamespace(
        helper=PromptStudioRegistryHelper,
        tool_processor=ToolProcessor,
        AdapterTypes=AdapterTypes,
        Spec=Spec,
        ToolUtils=ToolUtils,
    )


REAL_ADAPTER_ID = "11111111-2222-3333-4444-555555555555"
OTHER_ADAPTER_ID = "99999999-8888-7777-6666-555555555555"

PROFILE_LOOKUP = (
    "prompt_studio.prompt_studio_registry_v2.prompt_studio_registry_helper"
    ".ProfileManager.get_default_llm_profile"
)
ADAPTER_LOOKUP = "tool_instance_v2.tool_processor.AdapterProcessor.get_adapters_by_type"


def _make_tool(*, enable_challenge: bool, challenge_llm_id: str | None = None):
    """Minimal stand-in for ``CustomTool`` -- ``frame_spec`` reads only these."""
    tool = MagicMock(name="CustomTool")
    tool.tool_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    tool.description = "A tool exported from Prompt Studio"
    tool.enable_challenge = enable_challenge
    tool.challenge_llm = (
        None if challenge_llm_id is None else MagicMock(id=challenge_llm_id)
    )
    return tool


def _default_profile(llm_id: str = REAL_ADAPTER_ID):
    return MagicMock(llm=MagicMock(id=llm_id))


def _frame_spec(tool: Any) -> Any:
    deps = _deps()
    with patch(PROFILE_LOOKUP, return_value=_default_profile()):
        return deps.helper.frame_spec(tool=tool)


def _build_instance_schema(tool: Any) -> dict[str, Any]:
    """Compose export-time ``frame_spec`` with deploy-time enum injection.

    This is the path a tool instance's metadata is validated against:
    ``frame_spec`` output is persisted as ``tool_spec`` and later rehydrated
    via ``Spec.from_dict`` in ``get_tool_by_prompt_registry_id``.
    """
    deps = _deps()
    spec = _frame_spec(tool)
    adapters = [MagicMock(id=REAL_ADAPTER_ID, adapter_name="My LLM")]
    with patch(ADAPTER_LOOKUP, return_value=adapters):
        deps.tool_processor._update_schema_for_adapter_type(
            spec, spec.get_llm_adapter_properties_keys(), deps.AdapterTypes.LLM, None
        )
    return spec.to_dict()


def _seeded_metadata(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Seed instance metadata the way tool-instance creation really does.

    Calls the real ``ToolUtils.get_default_settings`` rather than reimplementing
    its type->zero-value table, so a change to the seeding rule surfaces here.
    """
    deps = _deps()
    tool = MagicMock()
    tool.spec = deps.Spec.from_dict(spec_dict)
    return deps.ToolUtils.get_default_settings(tool)


def _validation_errors(schema: dict[str, Any], instance: dict[str, Any]) -> list[Any]:
    return list(jsonschema.Draft7Validator(schema).iter_errors(instance))


@pytest.mark.parametrize("enable_challenge", [False, True])
class TestSeededInstanceDeploys:
    """A freshly created tool instance must pass deployment validation.

    This is the reported bug, and it fired regardless of ``enable_challenge``.
    """

    def test_seeded_metadata_validates(self, enable_challenge: bool) -> None:
        schema = _build_instance_schema(_make_tool(enable_challenge=enable_challenge))

        errors = _validation_errors(schema, _seeded_metadata(schema))

        assert errors == [], (
            "Metadata seeded by get_default_settings must pass deployment "
            f"validation; got {[e.validator for e in errors]}"
        )

    def test_seeded_challenge_llm_is_a_real_adapter_id(
        self, enable_challenge: bool
    ) -> None:
        """The seeded value must be usable, not merely valid."""
        schema = _build_instance_schema(_make_tool(enable_challenge=enable_challenge))

        assert _seeded_metadata(schema)["challenge_llm"] == REAL_ADAPTER_ID

    def test_adapter_type_is_always_declared(self, enable_challenge: bool) -> None:
        """``adapterType`` gates every adapter-aware path -- never drop it.

        Without it ``challenge_llm`` leaves ``get_llm_adapter_properties()``, so
        ``challenge_llm_adapter_id`` is never written and the settings form
        loses its adapter dropdown.
        """
        spec = _frame_spec(_make_tool(enable_challenge=enable_challenge))

        assert "challenge_llm" in spec.get_llm_adapter_properties_keys()
        assert "challenge_llm" in spec.get_llm_adapter_properties()

    def test_dropdown_metadata_is_present(self, enable_challenge: bool) -> None:
        """The settings form renders its dropdown from enum/enumNames."""
        schema = _build_instance_schema(_make_tool(enable_challenge=enable_challenge))
        prop = schema["properties"]["challenge_llm"]

        assert prop["enum"] == [REAL_ADAPTER_ID]
        assert prop["enumNames"] == ["My LLM"]

    def test_challenge_llm_stays_required(self, enable_challenge: bool) -> None:
        """Always seeded, so requiredness costs nothing and keeps the contract."""
        schema = _build_instance_schema(_make_tool(enable_challenge=enable_challenge))

        assert "challenge_llm" in schema["required"]


class TestChallengeLlmResolution:
    """``frame_spec`` seeds the same LLM the export path resolves."""

    def test_tool_challenge_llm_takes_precedence(self) -> None:
        deps = _deps()
        tool = _make_tool(enable_challenge=True, challenge_llm_id=OTHER_ADAPTER_ID)
        with patch(PROFILE_LOOKUP, return_value=_default_profile()) as get_default:
            spec = deps.helper.frame_spec(tool=tool)

        assert spec.properties["challenge_llm"]["default"] == OTHER_ADAPTER_ID
        get_default.assert_not_called()

    def test_falls_back_to_default_profile_llm(self) -> None:
        spec = _frame_spec(_make_tool(enable_challenge=False))

        assert spec.properties["challenge_llm"]["default"] == REAL_ADAPTER_ID


class TestInvalidValuesStillRejected:
    """The fix must not open a hole: a bad adapter must still fail."""

    @pytest.mark.parametrize("enable_challenge", [False, True])
    def test_empty_value_is_rejected(self, enable_challenge: bool) -> None:
        """A stored ``""`` -- the pre-fix state -- must not validate."""
        schema = _build_instance_schema(_make_tool(enable_challenge=enable_challenge))

        errors = _validation_errors(schema, {"challenge_llm": ""})

        assert any(
            e.validator == "enum" for e in errors
        ), f"Expected an enum violation, got {[e.validator for e in errors]}"

    def test_unknown_adapter_id_is_rejected(self) -> None:
        schema = _build_instance_schema(_make_tool(enable_challenge=True))

        errors = _validation_errors(schema, {"challenge_llm": OTHER_ADAPTER_ID})

        assert any(e.validator == "enum" for e in errors)

    def test_missing_key_is_rejected(self) -> None:
        schema = _build_instance_schema(_make_tool(enable_challenge=True))

        errors = _validation_errors(schema, {})

        assert any(e.validator == "required" for e in errors)
