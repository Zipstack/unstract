"""Create, delete and share events for shareable resources.

Adapters, connectors, workflows, API deployments, pipelines and Prompt Studio
projects (plus any other model in ``SHAREABLE_RESOURCES``). The target type is
the resource's ``kind`` from that registry, so the read API and the share
endpoints name a resource type the same way.
"""

from dataclasses import dataclass
from typing import Any

from tenant_account_v2.shareable_resources import descriptor_for_kind, kind_for_instance

from platform_audit.recorder import best_effort, record_platform_event

# The field that says what sort of resource it is, where the kind alone does
# not: an LLM vs an embedding adapter, an ETL vs a Task pipeline.
_SUBTYPE_FIELDS = {
    "adapter_instance": "adapter_type",
    "pipeline": "pipeline_type",
}


@dataclass(frozen=True)
class ResourceRef:
    kind: str
    id: str
    name: str
    subtype: str
    organization: Any


def resource_ref(resource: Any) -> ResourceRef | None:
    """What an event needs to name ``resource``, read now.

    Read it before deleting: a deleted row has no primary key.
    """
    kind = kind_for_instance(resource)
    if kind is None:
        return None
    descriptor = descriptor_for_kind(kind)
    subtype_field = _SUBTYPE_FIELDS.get(kind)
    return ResourceRef(
        kind=kind,
        id=str(getattr(resource, descriptor.id_field)),
        name=str(getattr(resource, descriptor.name_field, "") or ""),
        subtype=str(getattr(resource, subtype_field, "") or "") if subtype_field else "",
        organization=getattr(resource, "organization", None),
    )


@best_effort
def record_resource_event(
    request: Any,
    action: str,
    resource: Any,
    *,
    summary: str = "",
    changes: dict | None = None,
    metadata: dict | None = None,
) -> None:
    """Record ``action`` on ``resource`` (a model instance or a ``ResourceRef``).

    The summary defaults to the resource's subtype (``LLM``, ``ETL``).
    """
    ref = resource if isinstance(resource, ResourceRef) else resource_ref(resource)
    if ref is None:
        return
    record_platform_event(
        action=action,
        target_type=ref.kind,
        target_id=ref.id,
        target_name=ref.name,
        summary=summary or ref.subtype,
        changes=changes,
        metadata=metadata,
        request=request,
        organization=ref.organization,
    )


@best_effort
def record_sharing_change(
    request: Any,
    resource: Any,
    *,
    users: tuple[set, set] | None = None,
    groups: tuple[set, set] | None = None,
    shared_to_org: tuple[bool, bool] | None = None,
) -> None:
    """One ``resource.sharing_changed`` for a share request, if it changed anything.

    Each argument is the ``(before, after)`` of an axis the request touched:
    users and groups as model instances (stored as sorted e-mails and group
    names), ``shared_to_org`` as booleans. Untouched axes are ``None``.
    """
    from platform_audit.actions import Action

    sides: dict[str, dict] = {"before": {}, "after": {}}
    for axis, pair, label in (
        ("shared_users", users, lambda u: u.email),
        ("shared_groups", groups, lambda g: g.name),
    ):
        if pair is None or pair[0] == pair[1]:
            continue
        sides["before"][axis] = sorted(label(x) for x in pair[0])
        sides["after"][axis] = sorted(label(x) for x in pair[1])
    if shared_to_org is not None and shared_to_org[0] != shared_to_org[1]:
        sides["before"]["shared_to_org"] = shared_to_org[0]
        sides["after"]["shared_to_org"] = shared_to_org[1]
    if not sides["after"]:
        return
    record_resource_event(
        request, Action.RESOURCE_SHARING_CHANGED, resource, changes=sides
    )
