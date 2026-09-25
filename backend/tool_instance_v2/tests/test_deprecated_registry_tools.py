"""Registry tools (Classifier, Text Extractor) run on the deprecated Docker
runner: new workflows must not be able to pick them, while workflows that
already use one keep seeing it.

Unit tests: collaborators are patched per-test, so no database is touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.serializers import ValidationError

from tool_instance_v2 import serializers as _ser_mod
from tool_instance_v2 import tool_processor as _tp_mod

ToolProcessor = _tp_mod.ToolProcessor
ToolInstanceSerializer = _ser_mod.ToolInstanceSerializer

PROMPT_STUDIO_TOOL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
WORKFLOW_ID = "11111111-2222-3333-4444-555555555555"
REPO_TOOL_REGISTRY_CONFIG = (
    Path(__file__).resolve().parents[3] / "unstract/tool-registry/tool_registry_config"
)


@pytest.fixture
def repo_tool_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve tools from the repo's `public_tools.json`, not a deployed volume."""
    monkeypatch.setenv("TOOL_REGISTRY_CONFIG_PATH", str(REPO_TOOL_REGISTRY_CONFIG))


def _tool(function_name: str) -> dict[str, Any]:
    return {"name": function_name, "function_name": function_name}


def _function_names(tools: list[dict[str, Any]]) -> list[str]:
    return [tool["function_name"] for tool in tools]


@pytest.mark.usefixtures("repo_tool_registry")
class TestIsRegistryTool:
    """Reads the real `public_tools.json`, so a renamed tool id fails here."""

    @pytest.mark.parametrize("tool_uid", ["classify", "text_extractor"])
    def test_public_registry_tools_are_registry_tools(self, tool_uid: str) -> None:
        assert ToolProcessor.is_registry_tool(tool_uid)

    def test_prompt_studio_tool_is_not_a_registry_tool(self) -> None:
        assert not ToolProcessor.is_registry_tool(PROMPT_STUDIO_TOOL_ID)


class TestGetToolList:
    def _get_tool_list(self, tool_ids_in_workflow: set[str]) -> list[str]:
        registry = MagicMock()
        registry.fetch_tools_descriptions.return_value = [
            _tool("classify"),
            _tool("text_extractor"),
        ]
        with (
            patch.object(_tp_mod, "ToolRegistry", MagicMock(return_value=registry)),
            patch.object(_tp_mod, "IS_AGENTIC_REGISTRY_AVAILABLE", False),
            patch.object(
                _tp_mod.PromptStudioRegistryHelper,
                "fetch_json_for_registry",
                MagicMock(return_value=[_tool(PROMPT_STUDIO_TOOL_ID)]),
            ),
            patch.object(
                ToolProcessor,
                "_get_tool_ids_in_workflow",
                MagicMock(return_value=tool_ids_in_workflow),
            ),
        ):
            return _function_names(
                ToolProcessor.get_tool_list(MagicMock(name="user"), WORKFLOW_ID)
            )

    def test_registry_tools_are_hidden_from_a_workflow_without_them(self) -> None:
        assert self._get_tool_list(set()) == [PROMPT_STUDIO_TOOL_ID]

    def test_registry_tool_already_in_the_workflow_stays_listed(self) -> None:
        assert self._get_tool_list({"classify"}) == [
            "classify",
            PROMPT_STUDIO_TOOL_ID,
        ]

    def test_prompt_studio_tool_in_the_workflow_does_not_unhide_registry_tools(
        self,
    ) -> None:
        assert self._get_tool_list({PROMPT_STUDIO_TOOL_ID}) == [PROMPT_STUDIO_TOOL_ID]

    def test_no_workflow_means_no_tool_ids_and_no_query(self) -> None:
        with patch.object(_tp_mod.Workflow, "objects") as workflow_objects:
            assert ToolProcessor._get_tool_ids_in_workflow(MagicMock(), None) == set()
        workflow_objects.for_user.assert_not_called()


@pytest.mark.usefixtures("repo_tool_registry")
class TestCreateRejectsRegistryTools:
    def _create(self, tool_id: str) -> MagicMock:
        workflow = MagicMock(name="workflow")
        workflow.tool_instances.count.return_value = 0
        audit_create = MagicMock(return_value=MagicMock())
        with (
            patch.object(
                _ser_mod.Workflow,
                "objects",
                MagicMock(get=MagicMock(return_value=workflow)),
            ),
            patch.object(_ser_mod.ToolProcessor, "get_tool_by_uid", MagicMock()),
            patch.object(
                _ser_mod.ToolProcessor,
                "get_default_settings",
                MagicMock(return_value={}),
            ),
            patch.object(
                ToolInstanceSerializer, "_overlay_resolved_challenge_llm", MagicMock()
            ),
            patch.object(_ser_mod.AuditSerializer, "create", audit_create),
        ):
            ToolInstanceSerializer(context={"request": MagicMock()}).create(
                {"workflow_id": WORKFLOW_ID, "tool_id": tool_id}
            )
        return audit_create

    @pytest.mark.parametrize("tool_id", ["classify", "text_extractor"])
    def test_registry_tool_is_rejected(self, tool_id: str) -> None:
        with pytest.raises(ValidationError, match="deprecated"):
            self._create(tool_id)

    def test_prompt_studio_tool_is_created(self) -> None:
        self._create(PROMPT_STUDIO_TOOL_ID).assert_called_once()
