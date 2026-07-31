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
  4. Validation rejects ``""`` (an enum violation).

There is a second half to the bug, and it is why the seed alone was not enough:
``ToolInstanceViewSet.create`` calls ``update_metadata_with_default_values``
immediately after ``perform_create``, and ``challenge_llm`` is one of the LLM
adapter properties that walks. Before the guard added alongside these tests, it
unconditionally overwrote the key with the user's *default* LLM -- so the seed
was discarded for every user who has one, which is most of them.

Unit tests: the real modules are imported (Django is loaded by the rig's test
env, which sets ``DJANGO_SETTINGS_MODULE=backend.settings.test``) and every
collaborator is patched per-test, so no database is touched.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_registry_v2 import (
    prompt_studio_registry_helper as _psr_mod,
)
from prompt_studio.prompt_studio_registry_v2.constants import JsonSchemaKey

from tool_instance_v2 import serializers as _ser_mod
from tool_instance_v2 import tool_instance_helper as _tih_mod
from unstract.tool_registry.dto import Spec

PromptStudioRegistryHelper = _psr_mod.PromptStudioRegistryHelper
ToolInstanceSerializer = _ser_mod.ToolInstanceSerializer
ToolInstanceHelper = _tih_mod.ToolInstanceHelper

# The adapter ID the export resolved for the project's challenger LLM.
RESOLVED_CHALLENGE_LLM = "11111111-2222-3333-4444-555555555555"
# The deploying user's default LLM -- deliberately different, so a test can tell
# "kept the exported value" apart from "fell back to the user's default".
USER_DEFAULT_LLM = "99999999-8888-7777-6666-555555555555"

PROMPT_REGISTRY_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

CHALLENGE_LLM_ADAPTER_ID_KEY = "challenge_llm_adapter_id"


def _challenge_llm_property() -> dict[str, Any]:
    """The `challenge_llm` spec property exactly as `frame_spec` emits it."""
    return {
        "type": "string",
        "title": "Challenger LLM",
        "adapterType": "LLM",
        "description": "LLM to use for LLMChallenge",
        "adapterIdKey": CHALLENGE_LLM_ADAPTER_ID_KEY,
    }


def _make_tool() -> Any:
    """A `Tool` whose spec carries the adapter-valued `challenge_llm`."""
    tool = MagicMock(name="Tool")
    tool.spec = Spec(
        title="exported-tool",
        description="Exported prompt studio tool",
        required=[JsonSchemaKey.CHALLENGE_LLM],
        properties={
            JsonSchemaKey.CHALLENGE_LLM: _challenge_llm_property(),
            JsonSchemaKey.ENABLE_CHALLENGE: {
                "type": "boolean",
                "title": "Enable LLMChallenge",
                "default": False,
                "description": "Enables LLMChallenge",
            },
        },
    )
    return tool


def _spec_seeded_settings() -> dict[str, Any]:
    """What `get_default_settings` produces: no spec default -> seeded ""."""
    return {JsonSchemaKey.CHALLENGE_LLM: "", JsonSchemaKey.ENABLE_CHALLENGE: False}


def _exported_tool_settings() -> dict[str, Any]:
    """A realistic `tool_metadata[tool_settings]` block.

    Deliberately a *superset* of the spec: the export also writes `llm`,
    `vector-db`, `preamble` and friends, none of which belong in instance
    metadata.
    """
    return {
        JsonSchemaKey.CHALLENGE_LLM: RESOLVED_CHALLENGE_LLM,
        JsonSchemaKey.ENABLE_CHALLENGE: True,
        JsonSchemaKey.SUMMARIZE_AS_SOURCE: True,
        JsonSchemaKey.ENABLE_HIGHLIGHT: True,
        "llm": "aaaa1111-0000-0000-0000-000000000000",
        "vector-db": "bbbb2222-0000-0000-0000-000000000000",
        "preamble": "Extract carefully.",
    }


class TestChallengeLlmOverlay:
    """`_overlay_resolved_challenge_llm` seeds the real resolved adapter ID."""

    def test_resolved_value_replaces_the_empty_spec_seed(self) -> None:
        """The "" that fails enum validation is replaced by the real ID."""
        tool_settings = _spec_seeded_settings()
        with patch.object(
            PromptStudioRegistryHelper,
            "get_resolved_settings",
            return_value=_exported_tool_settings(),
        ):
            ToolInstanceSerializer._overlay_resolved_challenge_llm(
                _make_tool(), tool_settings, PROMPT_REGISTRY_ID
            )
        assert tool_settings[JsonSchemaKey.CHALLENGE_LLM] == RESOLVED_CHALLENGE_LLM

    def test_companion_adapter_id_key_is_written_too(self) -> None:
        """The `adapterIdKey` companion is set, matching every other path.

        `update_metadata_with_default_adapter` always writes the adapter key and
        its ID key together; seeding only one produces a metadata shape nothing
        else in the system emits.
        """
        tool_settings = _spec_seeded_settings()
        with patch.object(
            PromptStudioRegistryHelper,
            "get_resolved_settings",
            return_value=_exported_tool_settings(),
        ):
            ToolInstanceSerializer._overlay_resolved_challenge_llm(
                _make_tool(), tool_settings, PROMPT_REGISTRY_ID
            )
        assert tool_settings[CHALLENGE_LLM_ADAPTER_ID_KEY] == RESOLVED_CHALLENGE_LLM

    def test_only_challenge_llm_is_overlaid(self) -> None:
        """Scope guard: the four other spec/export overlaps stay untouched.

        The export's `tool_settings` also carries `enable_challenge`,
        `summarize_as_source` and `enable_highlight`, all of which are spec
        properties too. Overlaying them would change whether challenge and
        summarization actually run -- a separate, behaviour-affecting decision.
        """
        tool_settings = _spec_seeded_settings()
        with patch.object(
            PromptStudioRegistryHelper,
            "get_resolved_settings",
            return_value=_exported_tool_settings(),
        ):
            ToolInstanceSerializer._overlay_resolved_challenge_llm(
                _make_tool(), tool_settings, PROMPT_REGISTRY_ID
            )
        # Exported as True; must remain the spec default.
        assert tool_settings[JsonSchemaKey.ENABLE_CHALLENGE] is False
        # Non-spec export keys must never reach instance metadata.
        for key in ("llm", "vector-db", "preamble", JsonSchemaKey.SUMMARIZE_AS_SOURCE):
            assert key not in tool_settings

    def test_no_resolved_settings_is_a_no_op(self) -> None:
        """A non-Prompt-Studio tool resolves to {} and nothing changes."""
        tool_settings = _spec_seeded_settings()
        with patch.object(
            PromptStudioRegistryHelper, "get_resolved_settings", return_value={}
        ):
            ToolInstanceSerializer._overlay_resolved_challenge_llm(
                _make_tool(), tool_settings, "text_extractor"
            )
        assert tool_settings == _spec_seeded_settings()
        assert CHALLENGE_LLM_ADAPTER_ID_KEY not in tool_settings

    def test_empty_resolved_challenge_llm_does_not_overwrite(self) -> None:
        """An export carrying "" must not write "" plus a bogus ID key."""
        tool_settings = _spec_seeded_settings()
        with patch.object(
            PromptStudioRegistryHelper,
            "get_resolved_settings",
            return_value={JsonSchemaKey.CHALLENGE_LLM: ""},
        ):
            ToolInstanceSerializer._overlay_resolved_challenge_llm(
                _make_tool(), tool_settings, PROMPT_REGISTRY_ID
            )
        assert CHALLENGE_LLM_ADAPTER_ID_KEY not in tool_settings

    def test_tool_without_challenge_llm_skips_the_lookup(self) -> None:
        """No `challenge_llm` in the spec -> no registry query at all."""
        tool = _make_tool()
        tool.spec = Spec(
            title="plain-tool",
            description="A tool with no challenge LLM",
            required=[],
            properties={"some_setting": {"type": "string", "default": "x"}},
        )
        tool_settings = {"some_setting": "x"}
        with patch.object(
            PromptStudioRegistryHelper, "get_resolved_settings"
        ) as resolved_mock:
            ToolInstanceSerializer._overlay_resolved_challenge_llm(
                tool, tool_settings, PROMPT_REGISTRY_ID
            )
        resolved_mock.assert_not_called()


class TestOverlayIsWiredIntoCreate:
    """The overlay must actually be *called* by `create`.

    Without this, deleting the call from `create` while leaving the helper
    intact would keep every other test in this file green.
    """

    def test_create_invokes_the_overlay(self) -> None:
        workflow = MagicMock(name="Workflow")
        workflow.tool_instances.count.return_value = 0
        workflow.is_active = True

        validated_data: dict[str, Any] = {
            "workflow_id": "wf-1",
            "tool_id": PROMPT_REGISTRY_ID,
        }

        overlay_mock = MagicMock(name="_overlay_resolved_challenge_llm")
        with (
            patch.object(
                _ser_mod.Workflow,
                "objects",
                MagicMock(get=MagicMock(return_value=workflow)),
            ),
            patch.object(
                _ser_mod.ToolProcessor,
                "get_tool_by_uid",
                MagicMock(return_value=_make_tool()),
            ),
            patch.object(
                _ser_mod.ToolProcessor,
                "get_default_settings",
                MagicMock(return_value=_spec_seeded_settings()),
            ),
            patch.object(
                ToolInstanceSerializer,
                "_overlay_resolved_challenge_llm",
                overlay_mock,
            ),
            patch.object(
                _ser_mod.AuditSerializer, "create", MagicMock(return_value=MagicMock())
            ),
        ):
            ToolInstanceSerializer().create(validated_data)

        overlay_mock.assert_called_once()
        assert overlay_mock.call_args.args[2] == PROMPT_REGISTRY_ID


class TestDefaultAdapterDoesNotClobberSeededValue:
    """`update_metadata_with_default_adapter` must not stomp a seeded value.

    This is the half of the bug that made the seed a no-op in the common case:
    the walk runs right after creation and `challenge_llm` is an LLM adapter
    property, so a user with a default LLM had the exported value replaced.
    """

    @staticmethod
    def _run_default_adapter_walk(metadata: dict[str, Any]) -> dict[str, Any]:
        spec = Spec(
            title="exported-tool",
            description="Exported prompt studio tool",
            required=[JsonSchemaKey.CHALLENGE_LLM],
            properties={JsonSchemaKey.CHALLENGE_LLM: _challenge_llm_property()},
        )
        adapter = MagicMock(name="AdapterInstance")
        adapter.id = USER_DEFAULT_LLM
        ToolInstanceHelper.update_metadata_with_default_adapter(
            adapter_type=_tih_mod.AdapterTypes.LLM,
            schema_spec=spec,
            adapter=adapter,
            metadata=metadata,
        )
        return metadata

    def test_seeded_challenge_llm_survives_the_default_walk(self) -> None:
        """The exported value is kept, not replaced by the user's default."""
        metadata = self._run_default_adapter_walk(
            {
                JsonSchemaKey.CHALLENGE_LLM: RESOLVED_CHALLENGE_LLM,
                CHALLENGE_LLM_ADAPTER_ID_KEY: RESOLVED_CHALLENGE_LLM,
            }
        )
        assert metadata[JsonSchemaKey.CHALLENGE_LLM] == RESOLVED_CHALLENGE_LLM
        assert metadata[CHALLENGE_LLM_ADAPTER_ID_KEY] == RESOLVED_CHALLENGE_LLM

    def test_kept_value_never_leaves_a_half_written_pair(self) -> None:
        """Skipping the write must not strand a missing companion ID key.

        `update_metadata_with_adapter_properties` warns that a UUID-shaped value
        at the adapter key with no matching ID key "bypasses the lazy migrator
        and fails schema enum validation later". Preserving a value must not
        manufacture that shape.
        """
        metadata = self._run_default_adapter_walk(
            {JsonSchemaKey.CHALLENGE_LLM: RESOLVED_CHALLENGE_LLM}
        )
        assert metadata[JsonSchemaKey.CHALLENGE_LLM] == RESOLVED_CHALLENGE_LLM
        assert metadata[CHALLENGE_LLM_ADAPTER_ID_KEY] == RESOLVED_CHALLENGE_LLM

    def test_unset_challenge_llm_still_gets_the_user_default(self) -> None:
        """The guard fills gaps -- it must not disable the default entirely."""
        metadata = self._run_default_adapter_walk({JsonSchemaKey.CHALLENGE_LLM: ""})
        assert metadata[JsonSchemaKey.CHALLENGE_LLM] == USER_DEFAULT_LLM
        assert metadata[CHALLENGE_LLM_ADAPTER_ID_KEY] == USER_DEFAULT_LLM

    def test_absent_key_still_gets_the_user_default(self) -> None:
        """A key missing altogether is a gap too, and must be filled."""
        metadata = self._run_default_adapter_walk({})
        assert metadata[JsonSchemaKey.CHALLENGE_LLM] == USER_DEFAULT_LLM


class TestGetResolvedSettings:
    """The registry lookup reads the right block and stays quiet when normal."""

    def test_reads_the_tool_settings_block(self) -> None:
        settings_block = {JsonSchemaKey.CHALLENGE_LLM: RESOLVED_CHALLENGE_LLM}
        metadata = {
            JsonSchemaKey.TOOL_SETTINGS: settings_block,
            # A sibling key that must not be mistaken for the settings block.
            "outputs": [{"prompt": "x"}],
        }
        values_qs = MagicMock(name="values_list")
        values_qs.get.return_value = metadata
        with patch.object(
            _psr_mod.PromptStudioRegistry,
            "objects",
            MagicMock(values_list=MagicMock(return_value=values_qs)),
        ):
            resolved = PromptStudioRegistryHelper.get_resolved_settings(
                PROMPT_REGISTRY_ID
            )
        assert resolved == settings_block

    def test_non_uuid_tool_id_short_circuits_without_a_query(self) -> None:
        """Registry tools use slugs; those must not reach the DB or the log.

        `ToolInstance.tool_id` is a free-form CharField, so the common case --
        a built-in tool like "text_extractor" -- is not UUID-shaped at all.
        """
        objects_mock = MagicMock(name="objects")
        with patch.object(_psr_mod.PromptStudioRegistry, "objects", objects_mock):
            assert (
                PromptStudioRegistryHelper.get_resolved_settings("text_extractor") == {}
            )
        objects_mock.values_list.assert_not_called()

    def test_missing_registry_row_returns_empty(self) -> None:
        values_qs = MagicMock(name="values_list")
        values_qs.get.side_effect = _psr_mod.PromptStudioRegistry.DoesNotExist
        with patch.object(
            _psr_mod.PromptStudioRegistry,
            "objects",
            MagicMock(values_list=MagicMock(return_value=values_qs)),
        ):
            assert (
                PromptStudioRegistryHelper.get_resolved_settings(PROMPT_REGISTRY_ID) == {}
            )

    def test_row_without_tool_settings_returns_empty(self) -> None:
        values_qs = MagicMock(name="values_list")
        values_qs.get.return_value = None
        with patch.object(
            _psr_mod.PromptStudioRegistry,
            "objects",
            MagicMock(values_list=MagicMock(return_value=values_qs)),
        ):
            assert (
                PromptStudioRegistryHelper.get_resolved_settings(PROMPT_REGISTRY_ID) == {}
            )

    def test_db_errors_are_not_swallowed(self) -> None:
        """An `OperationalError` must propagate, not degrade to "".

        Swallowing it would seed "" and resurface much later as the same
        confusing 422 this change exists to prevent.
        """
        import pytest
        from django.db import OperationalError

        values_qs = MagicMock(name="values_list")
        values_qs.get.side_effect = OperationalError("db down")
        with patch.object(
            _psr_mod.PromptStudioRegistry,
            "objects",
            MagicMock(values_list=MagicMock(return_value=values_qs)),
        ):
            with pytest.raises(OperationalError):
                PromptStudioRegistryHelper.get_resolved_settings(PROMPT_REGISTRY_ID)
