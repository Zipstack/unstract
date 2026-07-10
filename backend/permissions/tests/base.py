"""Shared fixtures for co-owner (OWNER-membership) management tests (UN-2202).

One org with owner/co-owner/viewer/outsider/admin members, plus a builder table
for every OSS shareable resource so the owner-management surface can be exercised
uniformly. Mirrors ``tenant_account_v2.tests.GroupSharingTestBase``.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from account_v2.models import Organization, User
from permissions.permission import IsOwner
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

# Admin resolution is auth-plugin backed, so patch it to a deterministic
# predicate — the ``role="admin"`` membership row alone does not make
# ``_is_organization_admin`` true.
_ADMIN_PREDICATE = (
    "tenant_account_v2.organization_member_service."
    "OrganizationMemberService.is_user_organization_admin"
)


def make_user(email: str, **kwargs: Any) -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe(), **kwargs
    )


def _build_workflow(org: Organization, creator: User) -> Any:
    return Workflow.objects.create(
        workflow_name=f"wf-{secrets.token_hex(4)}", organization=org, created_by=creator
    )


def _build_custom_tool(org: Organization, creator: User) -> Any:
    from prompt_studio.prompt_studio_core_v2.models import CustomTool

    return CustomTool.objects.create(
        tool_name=f"tool-{secrets.token_hex(4)}",
        description="integration-test tool",
        organization=org,
        created_by=creator,
    )


def _build_adapter(org: Organization, creator: User) -> Any:
    from adapter_processor_v2.models import AdapterInstance

    return AdapterInstance.objects.create(
        adapter_name=f"adapter-{secrets.token_hex(4)}",
        adapter_id="openai|test",
        adapter_type="LLM",
        adapter_metadata={},
        organization=org,
        created_by=creator,
    )


def _build_connector(org: Organization, creator: User) -> Any:
    from connector_v2.models import ConnectorInstance

    return ConnectorInstance.objects.create(
        connector_name=f"conn-{secrets.token_hex(4)}",
        connector_id="test",
        organization=org,
        created_by=creator,
    )


def _build_pipeline(org: Organization, creator: User) -> Any:
    from pipeline_v2.models import Pipeline

    return Pipeline.objects.create(
        pipeline_name=f"pipe-{secrets.token_hex(4)}",
        workflow=_build_workflow(org, creator),
        organization=org,
        created_by=creator,
    )


def _build_api_deployment(org: Organization, creator: User) -> Any:
    from api_v2.models import APIDeployment

    # api_name defaults to a 36-char UUID; the column is shorter, so pass a
    # short unique name. save() derives api_endpoint from it.
    return APIDeployment.objects.create(
        api_name=f"api-{secrets.token_hex(4)}",
        workflow=_build_workflow(org, creator),
        organization=org,
        created_by=creator,
    )


@dataclass(frozen=True)
class ResourceSpec:
    """A shareable resource kind plus a builder returning a saved instance."""

    kind: str
    build: Callable[[Organization, User], Any]


# AgenticProject (7th shareable resource) is cloud-only — covered in the cloud
# repo's ``agentic_studio_v1`` test tree, which runs through the same rig.
RESOURCE_SPECS: list[ResourceSpec] = [
    ResourceSpec("workflow", _build_workflow),
    ResourceSpec("custom_tool", _build_custom_tool),
    ResourceSpec("adapter", _build_adapter),
    ResourceSpec("connector", _build_connector),
    ResourceSpec("pipeline", _build_pipeline),
    ResourceSpec("api_deployment", _build_api_deployment),
]


class CoOwnerOrgTestMixin:
    """setUp helper: one org, members, and a deterministic admin predicate."""

    def _seed_org(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.owner = make_user("owner@example.com")
        self.coowner = make_user("coowner@example.com")
        self.viewer = make_user("viewer@example.com")
        self.outsider = make_user("outsider@example.com")  # org member, no access
        self.admin = make_user("admin@example.com")
        self.stranger = make_user("stranger@example.com")  # NOT an org member
        for user in (self.owner, self.coowner, self.viewer, self.outsider):
            OrganizationMember.objects.create(
                organization=self.org, user=user, role="user"
            )
        OrganizationMember.objects.create(
            organization=self.org, user=self.admin, role="admin"
        )
        patcher = patch(
            _ADMIN_PREDICATE,
            side_effect=lambda u: getattr(u, "email", None) == self.admin.email,
        )
        patcher.start()
        # addCleanup is provided by TestCase (this is a mixin combined with it).
        self.addCleanup(patcher.stop)  # type: ignore[attr-defined]

    def _is_owner_perm(self, user: User, obj: object) -> bool:
        """Run ``IsOwner.has_object_permission`` for ``user`` against ``obj``."""
        request = APIRequestFactory().get("/")
        request.user = user
        return IsOwner().has_object_permission(request, APIView(), obj)
