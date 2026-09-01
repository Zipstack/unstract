"""Profile serializer resolves adapter FKs to display data without an access check.

The DRF base is patched out so the assertions cover only that resolution.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.serializers import AuditSerializer

from prompt_studio.prompt_profile_manager_v2.serializers import ProfileManagerSerializer


def _adapter(name: str, model: str) -> SimpleNamespace:
    return SimpleNamespace(adapter_name=name, model=model)


def _represent(instance: SimpleNamespace, base_rep: dict) -> dict:
    with (
        patch.object(AuditSerializer, "to_representation", return_value=base_rep),
        patch(
            "prompt_studio.prompt_profile_manager_v2.serializers."
            "AdapterProcessor.get_model_label",
            side_effect=lambda adapter: adapter.model,
        ),
        patch(
            "prompt_studio.prompt_profile_manager_v2.serializers."
            "AdapterProcessor.get_icon",
            return_value="/icons/adapter-icons/OpenAI.png",
        ),
    ):
        return ProfileManagerSerializer().to_representation(instance)


class ProfileDisplayInfoTests(unittest.TestCase):
    def test_display_info_resolved_without_adapter_access(self) -> None:
        instance = SimpleNamespace(
            profile_name="Prod",
            llm=_adapter("Shared GPT", "gpt-4o"),
            embedding_model=_adapter("Shared Embed", "text-embedding-3-small"),
            vector_store=_adapter("Shared Qdrant", "qdrant"),
            x2text=_adapter("Shared LLMW", "llmwhisperer"),
        )
        base_rep = {
            field: "some-uuid"
            for field in ("llm", "embedding_model", "vector_store", "x2text")
        }

        rep = _represent(instance, base_rep)

        self.assertEqual(
            rep["conf"],
            {
                "LLM": "gpt-4o",
                "Embedding Model": "text-embedding-3-small",
                "Vector Store": "qdrant",
                "Text Extractor": "llmwhisperer",
                "Profile Name": "Prod",
            },
        )
        # Only the LLM contributes the tile icon.
        self.assertEqual(rep["icon"], "/icons/adapter-icons/OpenAI.png")
        # FK ids are replaced by the adapter names.
        self.assertEqual(rep["llm"], "Shared GPT")

    def test_unset_adapters_are_skipped(self) -> None:
        instance = SimpleNamespace(
            profile_name="Half configured",
            llm=_adapter("Shared GPT", "gpt-4o"),
            embedding_model=None,
            vector_store=None,
            x2text=None,
        )

        rep = _represent(instance, {"llm": "some-uuid", "embedding_model": None})

        self.assertEqual(
            rep["conf"], {"LLM": "gpt-4o", "Profile Name": "Half configured"}
        )
        self.assertIsNone(rep["embedding_model"])

    def test_profile_with_no_adapters_has_empty_conf(self) -> None:
        instance = SimpleNamespace(
            profile_name="Empty",
            llm=None,
            embedding_model=None,
            vector_store=None,
            x2text=None,
        )

        rep = _represent(instance, {})

        # No "Profile Name" either - the tile has nothing to show.
        self.assertEqual(rep["conf"], {})
        self.assertNotIn("icon", rep)
