"""Adapter delete guard (UN-3598).

An adapter referenced by a workflow tool instance's ``metadata`` is held as
a plain JSON value, not an FK — the DB can't PROTECT it, so the view must
block the delete explicitly. These tests exercise that scan logic with the
ORM query mocked, so no test database is required.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from adapter_processor_v2.views import AdapterInstanceViewSet  # noqa: E402

ADAPTER_ID = "11111111-1111-1111-1111-111111111111"


def _adapter(adapter_id: str = ADAPTER_ID, name: str = "my-llm") -> SimpleNamespace:
    return SimpleNamespace(id=adapter_id, adapter_name=name, organization="org-1")


def _patch_metadatas(metadatas: list):
    """Stub ``ToolInstance.objects.filter(...).values_list(...)`` -> metadatas."""
    qs = MagicMock()
    qs.values_list.return_value = metadatas
    manager = MagicMock()
    manager.filter.return_value = qs
    return patch("adapter_processor_v2.views.ToolInstance.objects", manager)


def test_blocks_when_adapter_id_in_metadata():
    ad = _adapter()
    with _patch_metadatas([{"llmAdapterId": ADAPTER_ID, "chunkSize": 1024}]):
        assert AdapterInstanceViewSet._adapter_used_in_tool_instance(ad) is True


def test_blocks_when_adapter_name_in_metadata_pre_migration():
    # Before lazy migration, metadata holds the adapter NAME, not the id.
    ad = _adapter(name="prod-gpt4")
    with _patch_metadatas([{"llm": "prod-gpt4"}]):
        assert AdapterInstanceViewSet._adapter_used_in_tool_instance(ad) is True


def test_allows_when_unreferenced():
    ad = _adapter()
    with _patch_metadatas([{"llm": "some-other-adapter"}, {}]):
        assert AdapterInstanceViewSet._adapter_used_in_tool_instance(ad) is False


def test_ignores_empty_and_non_string_metadata_values():
    ad = _adapter()
    with _patch_metadatas([None, {}, {"chunkSize": 1024, "flag": True}]):
        assert AdapterInstanceViewSet._adapter_used_in_tool_instance(ad) is False


def test_blocks_when_adapter_id_nested_in_metadata():
    ad = _adapter()
    with _patch_metadatas([{"tool_settings": {"llmAdapterId": ADAPTER_ID}}]):
        assert AdapterInstanceViewSet._adapter_used_in_tool_instance(ad) is True


def test_handles_non_dict_metadata_without_error():
    # JSONField has no schema constraint, so corrupted/historical rows may hold
    # a list or scalar; the scan must not raise on them.
    ad = _adapter()
    with _patch_metadatas([[ADAPTER_ID], "some-string", 42]):
        assert AdapterInstanceViewSet._adapter_used_in_tool_instance(ad) is True
    with _patch_metadatas([["other"], "unrelated", 42]):
        assert AdapterInstanceViewSet._adapter_used_in_tool_instance(ad) is False
