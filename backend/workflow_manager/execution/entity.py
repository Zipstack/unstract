"""Which kind of source started a run: API deployment, ETL/TASK pipeline or workflow."""

from api_v2.models import APIDeployment
from django.db.models import Case, CharField, Exists, OuterRef, Q, Value, When
from pipeline_v2.models import Pipeline

from workflow_manager.execution.enum import ExecutionEntity

_PIPELINE_TYPES = {
    ExecutionEntity.ETL: Pipeline.PipelineType.ETL,
    ExecutionEntity.TASK: Pipeline.PipelineType.TASK,
}


def entity_condition(entity: ExecutionEntity) -> Exists | Q:
    """Condition matching executions started by ``entity``.

    EXISTS subqueries keep the check in SQL instead of fetching all ids.
    """
    if entity is ExecutionEntity.API:
        return Exists(APIDeployment.objects.filter(id=OuterRef("pipeline_id")))
    if entity is ExecutionEntity.WORKFLOW:
        return Q(pipeline_id__isnull=True)
    return Exists(
        Pipeline.objects.filter(
            id=OuterRef("pipeline_id"), pipeline_type=_PIPELINE_TYPES[entity]
        )
    )


def entity_annotation() -> Case:
    """Annotation naming each execution's entity; ``None`` when it matches none."""
    return Case(
        *(
            When(entity_condition(entity), then=Value(entity.value))
            for entity in ExecutionEntity
        ),
        default=Value(None),
        output_field=CharField(),
    )
