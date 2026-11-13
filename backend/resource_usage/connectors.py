"""References to connectors: workflow source and destination endpoints."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from resource_usage.constants import ConnectorRole, ItemType, ProfileKind, UsageGroup
from resource_usage.references import Reference, register_provider, relation_label


def workflow_endpoint_refs(connectors: Sequence[Any]) -> Iterable[tuple[Any, Reference]]:
    """Workflows that read from or write to the connector, with the role."""
    from workflow_manager.endpoint_v2.models import WorkflowEndpoint
    from workflow_manager.workflow_v2.models.workflow import Workflow

    roles = {
        WorkflowEndpoint.EndpointType.SOURCE: ConnectorRole.SOURCE,
        WorkflowEndpoint.EndpointType.DESTINATION: ConnectorRole.DESTINATION,
    }
    rows = WorkflowEndpoint._base_manager.filter(
        connector_instance__in=[connector.pk for connector in connectors]
    ).values_list(
        "connector_instance_id", "workflow_id", "workflow__workflow_name", "endpoint_type"
    )
    for connector_pk, workflow_id, workflow_name, endpoint_type in rows:
        yield (
            connector_pk,
            Reference(
                group=UsageGroup.WORKFLOWS,
                item_type=ItemType.WORKFLOW,
                model=Workflow,
                pk=workflow_id,
                name=workflow_name,
                role=roles.get(endpoint_type),
            ),
        )


def _claims() -> list[str]:
    from workflow_manager.endpoint_v2.models import WorkflowEndpoint

    return [relation_label(WorkflowEndpoint, "connector_instance")]


register_provider(ProfileKind.CONNECTOR, workflow_endpoint_refs, claims=_claims())
