"""Builders and a request helper shared by the global search tests."""

import secrets
from collections.abc import Callable
from typing import Any

from account_v2.models import Organization, User
from adapter_processor_v2.models import AdapterInstance
from api_v2.models import APIDeployment
from connector_v2.models import ConnectorInstance
from pipeline_v2.models import Pipeline
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from workflow_manager.workflow_v2.models.workflow import Workflow

from global_search.constants import OSSSearchType
from global_search.views import GlobalSearchView


def _workflow(org: Organization, user: User, name: str, description: str) -> Workflow:
    return Workflow.objects.create(
        workflow_name=name, description=description, organization=org, created_by=user
    )


def _parent(org: Organization, user: User, name: str) -> Workflow:
    # Random so the parent never matches a test query by accident.
    return _workflow(org, user, f"parent-{secrets.token_hex(4)}", "")


def build_prompt_studio_project(org, user, name, description=""):
    return CustomTool.objects.create(
        tool_name=name, description=description, organization=org, created_by=user
    )


def build_workflow(org, user, name, description=""):
    return _workflow(org, user, name, description)


def build_api_deployment(org, user, name, description=""):
    return APIDeployment.objects.create(
        display_name=name,
        api_name=f"api-{secrets.token_hex(4)}",
        description=description,
        workflow=_parent(org, user, name),
        organization=org,
        created_by=user,
    )


def _pipeline(pipeline_type: str) -> Callable[..., Pipeline]:
    def build(org, user, name, description=""):
        return Pipeline.objects.create(
            pipeline_name=name,
            pipeline_type=pipeline_type,
            workflow=_parent(org, user, name),
            organization=org,
            created_by=user,
        )

    return build


def build_adapter(org, user, name, description="", **overrides):
    fields = {
        "adapter_name": name,
        "adapter_id": "openai|test",
        "adapter_type": "LLM",
        "adapter_metadata": {},
        "description": description,
        "organization": org,
        "created_by": user,
    }
    fields.update(overrides)
    return AdapterInstance.objects.create(**fields)


def build_connector(org, user, name, description=""):
    return ConnectorInstance.objects.create(
        connector_name=name,
        connector_id="minio|c799f6e3-2b57-434e-aaac-b5daa415da19",
        organization=org,
        created_by=user,
    )


# Every OSS type, keyed by its contract type key.
OSS_BUILDERS: dict[str, Callable[..., Any]] = {
    OSSSearchType.PROMPT_STUDIO_PROJECT: build_prompt_studio_project,
    OSSSearchType.WORKFLOW: build_workflow,
    OSSSearchType.API_DEPLOYMENT: build_api_deployment,
    OSSSearchType.ETL_PIPELINE: _pipeline(Pipeline.PipelineType.ETL),
    OSSSearchType.TASK_PIPELINE: _pipeline(Pipeline.PipelineType.TASK),
    OSSSearchType.ADAPTER: build_adapter,
    OSSSearchType.CONNECTOR: build_connector,
}

# Types whose model has a description column the search matches.
DESCRIBED_TYPES = {
    OSSSearchType.PROMPT_STUDIO_PROJECT,
    OSSSearchType.WORKFLOW,
    OSSSearchType.API_DEPLOYMENT,
    OSSSearchType.ADAPTER,
}


def search(user: User, **params: Any) -> Response:
    request = APIRequestFactory().get("/search/", params)
    force_authenticate(request, user=user)
    return GlobalSearchView.as_view()(request)


def result_ids(response: Response, type_key: str | None = None) -> list[str]:
    return [
        result["id"]
        for group in response.data["groups"]
        if type_key is None or group["type"] == type_key
        for result in group["results"]
    ]
