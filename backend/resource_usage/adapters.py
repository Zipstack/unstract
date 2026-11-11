"""References to adapters: workflow tool instances and Prompt Studio."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from django.db.models import Q

from resource_usage.constants import OTHER_GROUP, ItemType, ProfileKind, UsageGroup
from resource_usage.references import Reference, register_provider, relation_label


def string_leaves(value: Any) -> Iterator[str]:
    """Every string nested anywhere in a JSON value.

    Walks values the way ``AdapterInstanceViewSet._adapter_used_in_tool_instance``
    does: dict values (not keys), list items, and strings; anything else is
    skipped. A test holds the two to the same answer.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from string_leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from string_leaves(item)


def tool_instance_refs(adapters: Sequence[Any]) -> Iterable[tuple[Any, Reference]]:
    """Workflows whose tool instances name the adapter in ``metadata``.

    As in the delete guard, a reference is the adapter's id or, before the
    lazy migration, its name, matched within the adapter's organisation.
    """
    from tool_instance_v2.models import ToolInstance
    from workflow_manager.workflow_v2.models.workflow import Workflow

    # (organization_id, id or name) -> adapter pks
    needles: dict[tuple[Any, str], list[Any]] = {}
    for adapter in adapters:
        for needle in (str(adapter.pk), adapter.adapter_name):
            needles.setdefault((adapter.organization_id, needle), []).append(adapter.pk)
    org_ids = {adapter.organization_id for adapter in adapters}

    rows = ToolInstance.objects.filter(workflow__organization_id__in=org_ids).values_list(
        "workflow_id", "workflow__workflow_name", "workflow__organization_id", "metadata"
    )
    for workflow_id, workflow_name, org_id, metadata in rows:
        matched: set[Any] = set()
        for leaf in string_leaves(metadata):
            matched.update(needles.get((org_id, leaf), ()))
        for adapter_pk in matched:
            yield (
                adapter_pk,
                Reference(
                    group=UsageGroup.WORKFLOWS,
                    item_type=ItemType.WORKFLOW,
                    model=Workflow,
                    pk=workflow_id,
                    name=workflow_name,
                ),
            )


_CUSTOM_TOOL_FIELDS = ("summarize_llm_adapter", "monitor_llm", "challenge_llm")
_PROFILE_FIELDS = ("vector_store", "embedding_model", "llm", "x2text")


def _any_of(fields: Sequence[str], pks: list[Any]) -> Q:
    query = Q()
    for name in fields:
        query |= Q(**{f"{name}__in": pks})
    return query


def prompt_studio_refs(adapters: Sequence[Any]) -> Iterable[tuple[Any, Reference]]:
    """Prompt Studio projects that use the adapter, directly or in a profile."""
    from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
    from prompt_studio.prompt_studio_core_v2.models import CustomTool

    pks = [adapter.pk for adapter in adapters]

    tools = CustomTool._base_manager.filter(_any_of(_CUSTOM_TOOL_FIELDS, pks))
    for tool_id, tool_name, *adapter_pks in tools.values_list(
        "tool_id", "tool_name", *(f"{name}_id" for name in _CUSTOM_TOOL_FIELDS)
    ):
        for adapter_pk in set(adapter_pks) - {None}:
            yield adapter_pk, _project_ref(CustomTool, tool_id, tool_name)

    profiles = ProfileManager._base_manager.filter(_any_of(_PROFILE_FIELDS, pks))
    for (
        profile_id,
        profile_name,
        tool_id,
        tool_name,
        *adapter_pks,
    ) in profiles.values_list(
        "profile_id",
        "profile_name",
        "prompt_studio_tool_id",
        "prompt_studio_tool__tool_name",
        *(f"{name}_id" for name in _PROFILE_FIELDS),
    ):
        for adapter_pk in set(adapter_pks) - {None}:
            if tool_id is None:
                # A profile with no project still blocks the delete.
                yield (
                    adapter_pk,
                    Reference(
                        group=OTHER_GROUP,
                        item_type=ItemType.PROMPT_STUDIO_PROFILE,
                        model=ProfileManager,
                        pk=profile_id,
                        name=profile_name,
                    ),
                )
            else:
                yield adapter_pk, _project_ref(CustomTool, tool_id, tool_name)


def _project_ref(model: Any, tool_id: Any, tool_name: str) -> Reference:
    return Reference(
        group=UsageGroup.PROMPT_STUDIO_PROJECTS,
        item_type=ItemType.PROMPT_STUDIO_PROJECT,
        model=model,
        pk=tool_id,
        name=tool_name,
    )


def _claims() -> list[str]:
    from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
    from prompt_studio.prompt_studio_core_v2.models import CustomTool

    return [relation_label(CustomTool, name) for name in _CUSTOM_TOOL_FIELDS] + [
        relation_label(ProfileManager, name) for name in _PROFILE_FIELDS
    ]


register_provider(ProfileKind.ADAPTER, tool_instance_refs)
register_provider(ProfileKind.ADAPTER, prompt_studio_refs, claims=_claims())
