"""Single source of truth for group-shareable resource models.

Both the org-membership cleanup signals and the group blast-radius view need to
know "what is shareable". Keeping two hardcoded lists let them drift (the cloud
``AgenticProject`` was missing from one). This registry holds string-only
descriptors so it is import-cheap and cycle-free; consumers resolve the actual
model lazily via ``django.apps.apps.get_model`` and skip apps absent from a
given deployment (e.g. the cloud-only agentic app in pure OSS).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ShareableResource:
    """Static descriptor for one group-shareable resource model."""

    app_label: str
    model_name: str
    kind: str  # serialization key surfaced in API payloads
    name_field: str  # human-readable display field
    id_field: str  # primary-key field name


# ``agentic_studio_v1`` is cloud-only; consumers resolve it lazily and skip it
# when the app is not installed.
SHAREABLE_RESOURCES: tuple[ShareableResource, ...] = (
    ShareableResource("workflow_v2", "Workflow", "workflow", "workflow_name", "id"),
    ShareableResource("pipeline_v2", "Pipeline", "pipeline", "pipeline_name", "id"),
    ShareableResource("api_v2", "APIDeployment", "api_deployment", "display_name", "id"),
    ShareableResource(
        "connector_v2", "ConnectorInstance", "connector_instance", "connector_name", "id"
    ),
    ShareableResource(
        "adapter_processor_v2",
        "AdapterInstance",
        "adapter_instance",
        "adapter_name",
        "id",
    ),
    ShareableResource(
        "prompt_studio_core_v2", "CustomTool", "custom_tool", "tool_name", "tool_id"
    ),
    ShareableResource(
        "agentic_studio_v1",
        "AgenticProject",
        "agentic_project",
        "project_name",
        "project_id",
    ),
)
