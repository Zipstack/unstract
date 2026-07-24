"""Regression tests for ``PromptStudioRegistryHelper.fetch_json_for_registry``.

Pins the fix that keeps the back-reference to the Prompt Studio project in the
tool registry listing.

Before the fix the projection carried only four keys -- ``name``,
``description``, ``icon``, ``function_name`` -- where ``function_name`` is the
``prompt_registry_id``, a fresh UUID unrelated to the Prompt Studio
``tool_id``. Callers were left correlating on ``name``, which is ambiguous
whenever two projects share one. The data was already present (``custom_tool``
is a ``OneToOneField`` and the serializer is ``fields = "__all__"``); the
projection simply dropped it.

The frontend shows the cost directly, in
``CreateApiDeploymentFromPromptStudio.jsx``::

    tool.function_name === toolDetails.tool_id || tool.name === toolDetails.tool_name

The first clause can never be true, so correlation silently falls through to
the ambiguous name comparison.

``fetch_json_for_registry`` is a pure projection over already-serialized data,
so these tests stub the ORM/serializer boundary and exercise the real loop
body. Django is not importable in a plain checkout (no ``pytest-django``), and
the helper module is Django-coupled, so the function body is extracted from
source -- mirroring ``prompt_studio_core_v2/tests/test_build_index_payload.py``.
If the function is renamed or restructured these tests fail rather than
silently skip.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
REGISTRY_DIR = BACKEND_DIR / "prompt_studio" / "prompt_studio_registry_v2"
REGISTRY_HELPER = REGISTRY_DIR / "prompt_studio_registry_helper.py"

START_MARKER = "    def fetch_json_for_registry(user: User) -> list[dict[str, Any]]:"

# A registry row as the serializer emits it: `custom_tool` is a OneToOneField,
# which DRF renders as the raw PK -- the Prompt Studio tool_id.
PROMPT_REGISTRY_ID = "99999999-8888-7777-6666-555555555555"
CUSTOM_TOOL_ID = "11111111-2222-3333-4444-555555555555"


def _load_json_schema_key() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_psr_constants_fetch", REGISTRY_DIR / "constants.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.JsonSchemaKey


JSON_SCHEMA_KEY = _load_json_schema_key()


def _real_fetch_json_for_registry(serialized_rows: list[dict[str, Any]]):
    """Extract the real function, stubbing only the ORM/serializer boundary."""
    source = REGISTRY_HELPER.read_text()
    if START_MARKER not in source:
        pytest.fail(
            f"Could not find {START_MARKER!r} in {REGISTRY_HELPER}. If it was "
            "renamed or restructured, update this test rather than deleting it."
        )
    body = source[source.index(START_MARKER) :]
    end = body.find("\n    @staticmethod")
    if end != -1:
        body = body[:end]
    body = textwrap.dedent(body).replace(
        "def fetch_json_for_registry(user: User) -> list[dict[str, Any]]:",
        "def fetch_json_for_registry(user):",
    )

    class _Manager:
        @staticmethod
        def list_tools(user: Any) -> list[dict[str, Any]]:
            return serialized_rows

    class _PromptStudioRegistry:
        objects = _Manager()

    class _Serializer:
        def __init__(self, instance: Any, many: bool = False) -> None:
            self.data = instance

    class _InternalError(Exception):
        pass

    class _Logger:
        @staticmethod
        def error(*args: Any, **kwargs: Any) -> None:
            return None

    namespace: dict[str, Any] = {
        "PromptStudioRegistry": _PromptStudioRegistry,
        "PromptStudioRegistrySerializer": _Serializer,
        "JsonSchemaKey": JSON_SCHEMA_KEY,
        "InternalError": _InternalError,
        "logger": _Logger,
        "Any": Any,
    }
    exec(compile(body, str(REGISTRY_HELPER), "exec"), namespace)
    return namespace["fetch_json_for_registry"]


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "name": "Invoice extractor",
        "description": "Extracts invoice fields",
        "icon": "icon-data",
        "prompt_registry_id": PROMPT_REGISTRY_ID,
        "custom_tool": CUSTOM_TOOL_ID,
    }
    row.update(overrides)
    return row


def test_listing_exposes_the_custom_tool_back_reference() -> None:
    """The fix: callers can correlate an entry with the project that made it."""
    fetch = _real_fetch_json_for_registry([_row()])

    (entry,) = fetch(user=object())

    assert entry["custom_tool"] == CUSTOM_TOOL_ID, (
        "The registry listing must carry the Prompt Studio tool_id, otherwise "
        "callers can only match on the ambiguous `name`"
    )


def test_function_name_remains_the_registry_id() -> None:
    """`function_name` is the registry UUID, NOT the Prompt Studio tool_id.

    Pins the distinction that makes the back-reference necessary in the first
    place, and guards against someone "fixing" the frontend's dead comparison by
    redefining `function_name` instead -- which would break tool resolution.
    """
    fetch = _real_fetch_json_for_registry([_row()])

    (entry,) = fetch(user=object())

    assert entry["function_name"] == PROMPT_REGISTRY_ID
    assert entry["function_name"] != entry["custom_tool"]


def test_existing_keys_are_preserved() -> None:
    """The change is additive -- current consumers must not break."""
    fetch = _real_fetch_json_for_registry([_row()])

    (entry,) = fetch(user=object())

    assert entry["name"] == "Invoice extractor"
    assert entry["description"] == "Extracts invoice fields"
    assert entry["icon"] == "icon-data"


def test_legacy_row_without_a_linked_project() -> None:
    """``custom_tool`` is nullable, so unlinked legacy rows report None.

    They must not raise, and must not be dropped from the listing.
    """
    fetch = _real_fetch_json_for_registry([_row(custom_tool=None)])

    (entry,) = fetch(user=object())

    assert entry["custom_tool"] is None
    assert entry["name"] == "Invoice extractor"


def test_rows_do_not_bleed_into_each_other() -> None:
    """The loop reuses a dict and resets it per row.

    A missing reset would smear one project's back-reference onto the next,
    which is worse than the original bug: callers would correlate confidently
    and wrongly.
    """
    other_registry_id = "aaaaaaaa-1111-2222-3333-444444444444"
    other_custom_tool = "bbbbbbbb-1111-2222-3333-444444444444"
    fetch = _real_fetch_json_for_registry(
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

    first, second = fetch(user=object())

    assert first["custom_tool"] == CUSTOM_TOOL_ID
    assert second["custom_tool"] == other_custom_tool
    assert first["function_name"] == PROMPT_REGISTRY_ID
    assert second["function_name"] == other_registry_id


def test_two_projects_sharing_a_name_stay_distinguishable() -> None:
    """The exact scenario the old projection could not represent."""
    duplicate_name = "Invoice extractor"
    fetch = _real_fetch_json_for_registry(
        [
            _row(name=duplicate_name),
            _row(
                name=duplicate_name,
                prompt_registry_id="cccccccc-1111-2222-3333-444444444444",
                custom_tool="dddddddd-1111-2222-3333-444444444444",
            ),
        ]
    )

    first, second = fetch(user=object())

    assert first["name"] == second["name"]
    assert first["custom_tool"] != second["custom_tool"], (
        "Two projects sharing a name must remain distinguishable by their "
        "back-reference -- this is the whole point of the fix"
    )
