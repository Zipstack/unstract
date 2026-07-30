"""Regression tests for ``PromptStudioRegistryHelper.fetch_json_for_registry``.

The registry listing served at ``tool/`` must carry ``tool_id`` -- the Prompt
Studio project that produced each entry. ``function_name`` cannot serve that
role: it is the ``prompt_registry_id``, a UUID minted per registry row and
unrelated to the project's ``tool_id``. Without ``tool_id`` the only correlator
left is ``name``, which is ambiguous whenever two projects share one.

The value is read from the ``custom_tool`` FK column and published under the
``tool_id`` key, matching what this identifier is called on every other public
surface (the API docs, and ``toolDetails.tool_id`` in the deployment UI). It is
stringified on the way out, so the listing does not depend on DRF's renderer to
turn a ``uuid.UUID`` into JSON.

Two properties are pinned deliberately, because both are load-bearing and
neither lives in the projection loop:

* ``PromptStudioRegistrySerializer`` must actually emit ``custom_tool``. It does
  so only because ``Meta.fields`` is ``"__all__"``. Narrowing that to an
  explicit list -- a plausible optimization, since ``"__all__"`` also ships the
  large ``tool_property``/``tool_spec``/``tool_metadata`` blobs on every listing
  -- would empty ``tool_id`` for every row without touching this projection at
  all. ``test_serializer_emits_the_custom_tool_column`` is what catches that.
* ``function_name`` must remain the registry UUID. "Fixing" a caller by
  redefining it would break tool resolution.

Collaborators are patched on the helper module per-test, so no database is
touched; the module itself is imported for real, as in the sibling suite
``prompt_studio_core_v2/tests/test_build_index_payload.py``.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_registry_v2 import (
    prompt_studio_registry_helper as _psr_mod,
)
from prompt_studio.prompt_studio_registry_v2.serializers import (
    PromptStudioRegistrySerializer,
)

PromptStudioRegistryHelper = _psr_mod.PromptStudioRegistryHelper

# DRF renders a OneToOneField through PrimaryKeyRelatedField, whose
# to_representation returns the raw pk -- a uuid.UUID, not a str. The fixtures
# use UUID objects for that reason; the projection is what stringifies.
PROMPT_REGISTRY_ID = uuid.UUID("99999999-8888-7777-6666-555555555555")
CUSTOM_TOOL_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _row(**overrides: Any) -> dict[str, Any]:
    """A registry row shaped as ``PromptStudioRegistrySerializer`` emits it."""
    row = {
        "name": "Invoice extractor",
        "description": "Extracts invoice fields",
        "icon": "icon-data",
        "prompt_registry_id": PROMPT_REGISTRY_ID,
        "custom_tool": CUSTOM_TOOL_ID,
    }
    row.update(overrides)
    return row


def _fetch(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run the real projection over ``rows``, stubbing the ORM and serializer.

    Patches land on the helper module, so the function under test is the real
    one -- a rename or restructure surfaces as an import error or a failing
    assertion here, never as a silent skip.
    """
    serializer = MagicMock(name="PromptStudioRegistrySerializer")
    serializer.return_value.data = rows
    with (
        patch.object(_psr_mod, "PromptStudioRegistry") as registry,
        patch.object(_psr_mod, "PromptStudioRegistrySerializer", serializer),
    ):
        registry.objects.list_tools.return_value = MagicMock(name="queryset")
        return PromptStudioRegistryHelper.fetch_json_for_registry(user=MagicMock())


def test_serializer_emits_the_custom_tool_column() -> None:
    """The projection can only publish what the serializer serializes.

    Pins the assumption the rest of this suite rests on. Without this, narrowing
    ``Meta.fields`` regresses the API to the pre-fix behaviour while every other
    test here still passes.
    """
    assert "custom_tool" in PromptStudioRegistrySerializer().get_fields(), (
        "PromptStudioRegistrySerializer must serialize `custom_tool`; without "
        "it fetch_json_for_registry publishes tool_id=None for every entry"
    )


def test_listing_exposes_the_prompt_studio_tool_id() -> None:
    """The fix: callers can correlate an entry with the project that made it."""
    (entry,) = _fetch([_row()])

    assert entry["tool_id"] == str(CUSTOM_TOOL_ID), (
        "The registry listing must carry the Prompt Studio tool_id, otherwise "
        "callers can only match on the ambiguous `name`"
    )


def test_function_name_remains_the_registry_id() -> None:
    """``function_name`` is the registry UUID, NOT the Prompt Studio tool_id.

    Pins the distinction that makes the back-reference necessary, and guards
    against someone "fixing" a caller by redefining ``function_name`` instead --
    which would break tool resolution.
    """
    (entry,) = _fetch([_row()])

    assert entry["function_name"] == PROMPT_REGISTRY_ID
    assert entry["function_name"] != entry["tool_id"]


def test_existing_keys_are_preserved() -> None:
    """The change is additive -- current consumers must not break."""
    (entry,) = _fetch([_row()])

    assert entry["name"] == "Invoice extractor"
    assert entry["description"] == "Extracts invoice fields"
    assert entry["icon"] == "icon-data"


def test_legacy_row_without_a_linked_project() -> None:
    """``custom_tool`` is nullable, so unlinked legacy rows report None.

    They must not raise, and must not be dropped from the listing.
    """
    (entry,) = _fetch([_row(custom_tool=None)])

    assert entry["tool_id"] is None
    assert entry["name"] == "Invoice extractor"


def test_rows_do_not_bleed_into_each_other() -> None:
    """The loop reuses a dict and resets it per row.

    A missing reset would smear one project's back-reference onto the next,
    which is worse than the original bug: callers would correlate confidently
    and wrongly.
    """
    other_registry_id = uuid.UUID("aaaaaaaa-1111-2222-3333-444444444444")
    other_custom_tool = uuid.UUID("bbbbbbbb-1111-2222-3333-444444444444")

    first, second = _fetch(
        [
            _row(),
            _row(
                name="Receipt extractor",
                description="Extracts receipt fields",
                icon="other-icon",
                prompt_registry_id=other_registry_id,
                custom_tool=other_custom_tool,
            ),
        ]
    )

    assert first["tool_id"] == str(CUSTOM_TOOL_ID)
    assert second["tool_id"] == str(other_custom_tool)
    assert first["function_name"] == PROMPT_REGISTRY_ID
    assert second["function_name"] == other_registry_id


def test_two_projects_sharing_a_name_stay_distinguishable() -> None:
    """The exact scenario the old projection could not represent."""
    duplicate_name = "Invoice extractor"

    first, second = _fetch(
        [
            _row(name=duplicate_name),
            _row(
                name=duplicate_name,
                prompt_registry_id=uuid.UUID("cccccccc-1111-2222-3333-444444444444"),
                custom_tool=uuid.UUID("dddddddd-1111-2222-3333-444444444444"),
            ),
        ]
    )

    assert first["name"] == second["name"]
    assert first["tool_id"] != second["tool_id"], (
        "Two projects sharing a name must remain distinguishable by their "
        "back-reference -- this is the whole point of the fix"
    )
