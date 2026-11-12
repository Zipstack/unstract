"""References to adapters: workflow tool instances and Prompt Studio."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from django.contrib.postgres.fields import ArrayField
from django.db.models import F, Func, Q, TextField, Value

from resource_usage.constants import OTHER_GROUP, ItemType, ProfileKind, UsageGroup
from resource_usage.references import Reference, register_provider, relation_label


class _StringLeavesIn(Func):
    """The distinct strings anywhere in a JSON value that equal one of ``needles``.

    Reads the JSON the way the delete guard walks it
    (``AdapterInstanceViewSet._adapter_used_in_tool_instance``): object values
    and array items, never keys, compared by equality. Postgres can hash that
    test for a constant array (psycopg2 sends the list inline), so the cost
    barely grows with the number of needles. Only the matched strings are sent
    back, not the whole JSON value.
    """

    arity = 2
    output_field = ArrayField(TextField())

    def as_sql(
        self, compiler: Any, connection: Any, **extra_context: Any
    ) -> tuple[str, tuple[Any, ...]]:
        json_value, needles = self.get_source_expressions()
        json_sql, json_params = compiler.compile(json_value)
        needles_sql, needles_params = compiler.compile(needles)
        sql = (
            "ARRAY(SELECT DISTINCT leaf #>> '{}'"
            f" FROM jsonb_path_query({json_sql},"
            " 'strict $.** ? (@.type() == \"string\")') AS leaf"
            f" WHERE leaf #>> '{{}}' = ANY({needles_sql}))"
        )
        return sql, (*json_params, *needles_params)


def tool_instance_refs(adapters: Sequence[Any]) -> Iterable[tuple[Any, Reference]]:
    """Workflows whose tool instances name the adapter in ``metadata``.

    As in the delete guard, a reference is the adapter's id or, before the
    lazy migration, its name, matched within the adapter's organisation.
    """
    from tool_instance_v2.models import ToolInstance

    # (organization_id, id or name) -> adapter pks
    needles: dict[tuple[Any, str], list[Any]] = {}
    for adapter in adapters:
        for needle in (str(adapter.pk), adapter.adapter_name):
            needles.setdefault((adapter.organization_id, needle), []).append(adapter.pk)
    if not needles:
        return
    matched_leaves = _StringLeavesIn(
        F("metadata"),
        Value([key[1] for key in needles], output_field=ArrayField(TextField())),
    )
    # Rows naming no needle get an empty array (length 0) and drop out.
    rows = (
        ToolInstance.objects.filter(
            workflow__organization_id__in={key[0] for key in needles}
        )
        .annotate(matched=matched_leaves)
        .filter(matched__len__gt=0)
        .values_list(
            "workflow_id",
            "workflow__workflow_name",
            "workflow__organization_id",
            "matched",
        )
    )
    for workflow_id, workflow_name, org_id, matched in rows:
        adapter_pks = {pk for leaf in matched for pk in needles.get((org_id, leaf), ())}
        for adapter_pk in adapter_pks:
            yield adapter_pk, _workflow_ref(workflow_id, workflow_name)


def _workflow_ref(workflow_id: Any, workflow_name: str) -> Reference:
    from workflow_manager.workflow_v2.models.workflow import Workflow

    return Reference(
        group=UsageGroup.WORKFLOWS,
        item_type=ItemType.WORKFLOW,
        model=Workflow,
        pk=workflow_id,
        name=workflow_name,
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
