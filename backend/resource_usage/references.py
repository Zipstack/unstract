"""What references an adapter or connector, gathered in a fixed number of
queries however many profiles are asked about.

A reference that makes the delete guard refuse the profile is
``blocks_delete=True``. The guard refuses on two things, and both are covered
here: a ``PROTECT``/``RESTRICT`` foreign key (Django raises ``ProtectedError``)
and, for adapters, a value in a workflow tool instance's ``metadata``
(``AdapterInstanceViewSet._adapter_used_in_tool_instance``).

Providers turn known relations into named, routable items. Any
``PROTECT``/``RESTRICT`` relation no provider claims is still reported, in the
``other`` group, so a profile the guard refuses is never reported as unused.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from django.db import models
from django.db.models import Model

from resource_usage.constants import (
    OTHER_GROUP,
    ConnectorRole,
    ItemType,
    ProfileKind,
    UsageGroup,
    UsedAs,
)


@dataclass
class Reference:
    """One thing that uses a profile."""

    group: str
    item_type: str
    model: type[Model]
    pk: Any
    name: str | None
    role: str | None = None
    # True when this reference makes the delete guard refuse the profile.
    blocks_delete: bool = True
    # False for items reached through another item (a workflow's
    # deployments and pipelines); those are listed but not counted.
    direct: bool = True

    @property
    def key(self) -> tuple[str, str]:
        return (self.group, str(self.pk))

    def merge(self, other: Reference) -> None:
        self.blocks_delete = self.blocks_delete or other.blocks_delete
        self.direct = self.direct or other.direct
        if self.role != other.role:
            self.role = _merge_roles(self.role, other.role)


def _merge_roles(first: str | None, second: str | None) -> str | None:
    roles = {role for role in (first, second) if role}
    if not roles:
        return None
    if len(roles) == 1:
        return roles.pop()
    return ConnectorRole.BOTH


@dataclass
class ProfileUsage:
    """Everything that references one profile."""

    references: dict[tuple[str, str], Reference] = field(default_factory=dict)

    def add(self, reference: Reference) -> None:
        existing = self.references.get(reference.key)
        if existing:
            existing.merge(reference)
        else:
            self.references[reference.key] = reference

    @property
    def counted(self) -> list[Reference]:
        # Non-blocking references (Agentic Studio projects, whose FKs are
        # SET_NULL) are counted too: deleting the profile would still break
        # them, so the profile is not reported as unused.
        return [ref for ref in self.references.values() if ref.direct]

    @property
    def used_in_count(self) -> int:
        return len(self.counted)

    @property
    def blocks_delete(self) -> bool:
        return any(ref.blocks_delete for ref in self.references.values())

    @property
    def used_as(self) -> str:
        roles: set[str] = set()
        for ref in self.counted:
            if ref.role == ConnectorRole.BOTH:
                roles |= {ConnectorRole.SOURCE, ConnectorRole.DESTINATION}
            elif ref.role:
                roles.add(ref.role)
        if roles >= {ConnectorRole.SOURCE, ConnectorRole.DESTINATION}:
            return UsedAs.BOTH
        if roles:
            return UsedAs(roles.pop())
        return UsedAs.NONE


# A provider yields ``(profile_pk, reference)`` for the given profiles.
Provider = Callable[[Sequence[Model]], Iterable[tuple[Any, Reference]]]


@dataclass(frozen=True)
class _Registration:
    provider: Provider
    # "app_label.ModelName.field_name" of each FK the provider reports, so the
    # generic PROTECT fallback skips it.
    claims: frozenset[str]


_providers: dict[str, list[_Registration]] = {kind: [] for kind in ProfileKind}


def register_provider(
    kind: ProfileKind | str, provider: Provider, claims: Iterable[str] = ()
) -> None:
    """Add a source of references for adapters or connectors.

    The cloud backend calls this from an ``AppConfig.ready()`` to contribute
    its own references. Registering the same provider twice has no effect.
    """
    registrations = _providers[ProfileKind(kind)]
    if any(reg.provider is provider for reg in registrations):
        return
    registrations.append(_Registration(provider, frozenset(claims)))


def unregister_provider(kind: ProfileKind | str, provider: Provider) -> None:
    """Remove a provider; for tests."""
    registrations = _providers[ProfileKind(kind)]
    registrations[:] = [reg for reg in registrations if reg.provider is not provider]


def relation_label(model: type[Model], field_name: str) -> str:
    return f"{model._meta.label}.{field_name}"


_BLOCKING = (models.PROTECT, models.RESTRICT)


def blocking_relations(profile_model: type[Model]) -> list[Any]:
    """Every relation whose rows make deleting a profile raise."""
    return [
        rel
        for rel in profile_model._meta.related_objects
        if getattr(rel, "on_delete", None) in _BLOCKING
    ]


def _unclaimed_relation_refs(
    kind: ProfileKind, profiles: Sequence[Model]
) -> Iterable[tuple[Any, Reference]]:
    claimed = set().union(*(reg.claims for reg in _providers[kind]))
    pks = [profile.pk for profile in profiles]
    for rel in blocking_relations(type(profiles[0])):
        if relation_label(rel.related_model, rel.field.name) in claimed:
            continue
        # The base manager, as the delete collector uses: no org scoping.
        rows = rel.related_model._base_manager.filter(
            **{f"{rel.field.name}__in": pks}
        ).values_list("pk", rel.field.attname)
        for pk, profile_pk in rows:
            yield (
                profile_pk,
                Reference(
                    group=OTHER_GROUP,
                    item_type=rel.related_model._meta.model_name,
                    model=rel.related_model,
                    pk=pk,
                    name=None,
                ),
            )


def _derived_refs(index: dict[Any, ProfileUsage]) -> None:
    """Add each used workflow's API deployments and pipelines."""
    from api_v2.models import APIDeployment
    from pipeline_v2.models import Pipeline
    from workflow_manager.workflow_v2.models.workflow import Workflow

    workflow_refs: dict[str, list[tuple[ProfileUsage, Reference]]] = {}
    for usage in index.values():
        for ref in list(usage.references.values()):
            if ref.model is Workflow:
                workflow_refs.setdefault(str(ref.pk), []).append((usage, ref))
    if not workflow_refs:
        return

    deployments = APIDeployment._base_manager.filter(
        workflow_id__in=workflow_refs
    ).values_list("id", "display_name", "workflow_id")
    for pk, name, workflow_id in deployments:
        for usage, workflow_ref in workflow_refs[str(workflow_id)]:
            usage.add(
                Reference(
                    group=UsageGroup.DEPLOYMENTS,
                    item_type=ItemType.API_DEPLOYMENT,
                    model=APIDeployment,
                    pk=pk,
                    name=name,
                    role=workflow_ref.role,
                    blocks_delete=False,
                    direct=False,
                )
            )

    pipelines = Pipeline._base_manager.filter(workflow_id__in=workflow_refs).values_list(
        "id", "pipeline_name", "workflow_id"
    )
    for pk, name, workflow_id in pipelines:
        for usage, workflow_ref in workflow_refs[str(workflow_id)]:
            usage.add(
                Reference(
                    group=UsageGroup.PIPELINES,
                    item_type=ItemType.PIPELINE,
                    model=Pipeline,
                    pk=pk,
                    name=name,
                    role=workflow_ref.role,
                    blocks_delete=False,
                    direct=False,
                )
            )


def collect(
    kind: ProfileKind | str,
    profiles: Sequence[Model],
    *,
    with_derived: bool = False,
) -> dict[Any, ProfileUsage]:
    """Usage of each profile, keyed by its pk.

    ``with_derived`` adds the deployments and pipelines of each used workflow;
    the lists leave it off, as those are never counted.
    """
    # Providers register on import of these modules.
    from resource_usage import adapters, connectors  # noqa: F401

    kind = ProfileKind(kind)
    index: dict[Any, ProfileUsage] = {profile.pk: ProfileUsage() for profile in profiles}
    if not profiles:
        return index

    sources: list[Iterable[tuple[Any, Reference]]] = [
        reg.provider(profiles) for reg in _providers[kind]
    ]
    sources.append(_unclaimed_relation_refs(kind, profiles))
    for source in sources:
        for profile_pk, reference in source:
            usage = index.get(profile_pk)
            if usage is not None:
                usage.add(reference)

    if with_derived:
        _derived_refs(index)
    return index
