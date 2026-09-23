"""Shared "is this exported tool still in use?" logic.

Two delete paths need the same answer: deleting a Prompt Studio project
(``prompt_studio_core_v2``) and unpublishing its exported tool
(``prompt_studio_registry_v2``). Both refuse when a workflow still references
the registry row, and both want to name *where* it is referenced.

Keeping one copy matters because the set of deployment kinds is open — adding a
fourth would otherwise leave one caller silently reporting a stale set, telling
the user to clear usages in the wrong places.
"""

from api_v2.models import APIDeployment
from pipeline_v2.models import Pipeline
from tool_instance_v2.models import ToolInstance
from workflow_manager.endpoint_v2.models import WorkflowEndpoint

from prompt_studio.prompt_studio_core_v2.constants import DeploymentType


def dependent_workflow_ids(registry_pk: str) -> set:
    """Workflow IDs whose tool instances reference ``registry_pk``.

    An exported tool's ``ToolInstance.tool_id`` is its ``prompt_registry_id``,
    stored as a plain ``CharField`` rather than a foreign key -- which is why
    the database cannot enforce this and callers must check explicitly.
    """
    return set(
        ToolInstance.objects.filter(tool_id=registry_pk)
        .values_list("workflow_id", flat=True)
        .distinct()
    )


def deployment_types_for(workflow_ids: set) -> set:
    """Name the deployment kinds reachable from ``workflow_ids``.

    Inactive deployments count: they still reference the tool and would break
    on re-activation.
    """
    deployment_types: set = set()
    if not workflow_ids:
        return deployment_types

    if APIDeployment.objects.filter(workflow_id__in=workflow_ids).exists():
        deployment_types.add(DeploymentType.API_DEPLOYMENT)

    pipeline_type_mapping = {
        Pipeline.PipelineType.ETL: DeploymentType.ETL_PIPELINE,
        Pipeline.PipelineType.TASK: DeploymentType.TASK_PIPELINE,
    }
    pipeline_types = (
        Pipeline.objects.filter(workflow_id__in=workflow_ids)
        .values_list("pipeline_type", flat=True)
        .distinct()
    )
    for pipeline_type in pipeline_types:
        if pipeline_type in pipeline_type_mapping:
            deployment_types.add(pipeline_type_mapping[pipeline_type])

    if WorkflowEndpoint.objects.filter(
        workflow_id__in=workflow_ids,
        connection_type=WorkflowEndpoint.ConnectionType.MANUALREVIEW,
    ).exists():
        deployment_types.add(DeploymentType.HUMAN_QUALITY_REVIEW)

    return deployment_types


def join_deployment_types(deployment_types: set) -> str:
    """Render deployment kinds as an English list ("A", "A or B", "A, B, or C").

    Returns an empty string for an empty set so callers can choose their own
    fallback wording.
    """
    if not deployment_types:
        return ""
    types_list = sorted(deployment_types)
    if len(types_list) == 1:
        return types_list[0]
    if len(types_list) == 2:
        return f"{types_list[0]} or {types_list[1]}"
    return ", ".join(types_list[:-1]) + f", or {types_list[-1]}"
