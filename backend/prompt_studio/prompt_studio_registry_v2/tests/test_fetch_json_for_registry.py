"""Regression tests for ``PromptStudioRegistryHelper.fetch_json_for_registry``.

The registry listing served at ``tool/`` must carry ``prompt_studio_tool_id``
-- the Prompt Studio project that produced each entry. ``function_name`` cannot
serve that role: it is the ``prompt_registry_id``, a UUID minted per registry
row and unrelated to the project's id. Without the back-reference the only
correlator left is ``name``, which is ambiguous whenever two projects share one.

The key is deliberately not ``tool_id``: consumers of this listing also POST to
``tool_instance/``, where ``tool_id`` means the tool's *function name*
(``ToolInstance.tool_id``), so that name already has an incompatible meaning in
the same call path.

The two serialized fields this suite handles have different DRF field classes,
and therefore different Python types on the way out -- the fixtures model each
as the real serializer emits it:

* ``prompt_registry_id`` is a ``models.UUIDField`` -> DRF ``UUIDField``, whose
  ``to_representation`` returns a ``str``.
* ``custom_tool`` is a ``OneToOneField`` -> DRF ``PrimaryKeyRelatedField``,
  whose ``to_representation`` returns the raw pk -- a ``uuid.UUID``.

Two properties are pinned deliberately, because neither lives in the projection
loop:

* ``PromptStudioRegistrySerializer`` must actually emit ``custom_tool``. It does
  so only because ``Meta.fields`` is ``"__all__"``. Narrowing that to an
  explicit list -- a plausible optimization, since ``"__all__"`` also ships the
  large ``tool_property``/``tool_spec``/``tool_metadata`` blobs on every listing
  -- would empty the back-reference for every row without touching this
  projection at all. ``test_serializer_emits_the_custom_tool_column`` asserts
  against rendered output rather than the declared field set, so a
  ``to_representation`` override that drops the key is caught too.
* ``function_name`` must remain the registry UUID. "Fixing" a caller by
  redefining it would break tool resolution.

Collaborators are patched on the helper module per-test, so no database is
touched. The module is imported for real, which means this file needs Django
configured -- it runs in the rig's ``unit-backend`` tier, where
``DJANGO_SETTINGS_MODULE`` is set (``tests/groups.yaml``). Under a bare
``pytest`` with no settings module it fails at collection, as every
Django-coupled suite here does.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from prompt_studio.prompt_studio_registry_v2 import (
    prompt_studio_registry_helper as _psr_mod,
)
from prompt_studio.prompt_studio_registry_v2.serializers import (
    PromptStudioRegistrySerializer,
)

PromptStudioRegistryHelper = _psr_mod.PromptStudioRegistryHelper

# Typed as the real serializer emits each field -- see the module docstring.
PROMPT_REGISTRY_ID = str(uuid.UUID("99999999-8888-7777-6666-555555555555"))
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
    assertion here, never as a silent skip. The serializer's call shape is
    asserted too: dropping ``many=True`` would make DRF treat the queryset as a
    single instance and break the listing in production.
    """
    user = MagicMock(name="user")
    serializer = MagicMock(name="PromptStudioRegistrySerializer")
    serializer.return_value.data = rows
    with (
        patch.object(_psr_mod, "PromptStudioRegistry") as registry,
        patch.object(_psr_mod, "PromptStudioRegistrySerializer", serializer),
    ):
        queryset = MagicMock(name="queryset")
        registry.objects.list_tools.return_value = queryset

        result = PromptStudioRegistryHelper.fetch_json_for_registry(user=user)

        registry.objects.list_tools.assert_called_once_with(user)
        serializer.assert_called_once_with(instance=queryset, many=True)
    return result


def test_serializer_emits_the_custom_tool_column() -> None:
    """The projection can only publish what the serializer serializes.

    Drives the serializer's real ``to_representation`` rather than inspecting
    ``get_fields()``, so both ways the key can vanish are caught: narrowing
    ``Meta.fields``, and an override that drops it on the way out. Rendering a
    plain stub keeps this DB-free -- a real instance would make
    ``PrimaryKeyRelatedField`` evaluate its queryset.
    """
    stub = SimpleNamespace(
        prompt_registry_id=uuid.UUID(PROMPT_REGISTRY_ID),
        custom_tool=SimpleNamespace(pk=CUSTOM_TOOL_ID),
        name="Invoice extractor",
        description="Extracts invoice fields",
        icon="icon-data",
    )
    serializer = PromptStudioRegistrySerializer()
    fields = {
        name: field
        for name, field in serializer.get_fields().items()
        if not field.write_only and hasattr(stub, name)
    }

    rendered = {
        name: field.to_representation(getattr(stub, name))
        for name, field in fields.items()
    }

    assert "custom_tool" in rendered, (
        "PromptStudioRegistrySerializer must serialize `custom_tool`; without "
        "it fetch_json_for_registry publishes prompt_studio_tool_id=None for "
        "every entry"
    )
    assert (
        rendered["custom_tool"] == CUSTOM_TOOL_ID
    ), "custom_tool must render as the raw pk; the projection stringifies it"
    assert isinstance(rendered["prompt_registry_id"], str), (
        "prompt_registry_id renders as a str, which is why the fixtures in "
        "this file model it as one"
    )


def test_listing_exposes_the_prompt_studio_tool_id() -> None:
    """The fix: callers can correlate an entry with the project that made it."""
    (entry,) = _fetch([_row()])

    assert entry["prompt_studio_tool_id"] == str(CUSTOM_TOOL_ID), (
        "The registry listing must carry the Prompt Studio project id, "
        "otherwise callers can only match on the ambiguous `name`"
    )


def test_function_name_remains_the_registry_id() -> None:
    """``function_name`` is the registry UUID, NOT the Prompt Studio project id.

    Pins the distinction that makes the back-reference necessary, and guards
    against someone "fixing" a caller by redefining ``function_name`` instead --
    which would break tool resolution. Both sides are compared as strings so the
    inequality cannot pass on a type mismatch alone.
    """
    (entry,) = _fetch([_row()])

    assert entry["function_name"] == PROMPT_REGISTRY_ID
    assert entry["function_name"] != entry["prompt_studio_tool_id"]


def test_the_two_ids_are_compared_like_for_like() -> None:
    """A same-identifier collision must be detectable, not hidden by types.

    If both keys ever carried the same id, the guard in
    ``test_function_name_remains_the_registry_id`` has to fail. That only holds
    when the two values share a Python type; a ``UUID``-vs-``str`` mismatch
    would make the guard pass no matter what the values were.
    """
    shared = uuid.UUID("11111111-2222-3333-4444-555555555555")
    (entry,) = _fetch([_row(prompt_registry_id=str(shared), custom_tool=shared)])

    assert entry["function_name"] == entry["prompt_studio_tool_id"], (
        "Both keys must be rendered as the same type, so that comparing them "
        "is meaningful rather than trivially true"
    )


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

    assert entry["prompt_studio_tool_id"] is None
    assert entry["name"] == "Invoice extractor"


def test_rows_do_not_bleed_into_each_other() -> None:
    """The loop reuses a dict and resets it per row.

    A missing reset would smear one project's back-reference onto the next,
    which is worse than the original bug: callers would correlate confidently
    and wrongly.
    """
    other_registry_id = str(uuid.UUID("aaaaaaaa-1111-2222-3333-444444444444"))
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

    assert first["prompt_studio_tool_id"] == str(CUSTOM_TOOL_ID)
    assert second["prompt_studio_tool_id"] == str(other_custom_tool)
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
                prompt_registry_id=str(uuid.UUID("cccccccc-1111-2222-3333-444444444444")),
                custom_tool=uuid.UUID("dddddddd-1111-2222-3333-444444444444"),
            ),
        ]
    )

    assert first["name"] == second["name"]
    assert first["prompt_studio_tool_id"] != second["prompt_studio_tool_id"], (
        "Two projects sharing a name must remain distinguishable by their "
        "back-reference -- this is the whole point of the fix"
    )
