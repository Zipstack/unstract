"""Behaviour of the organization-scoped read-only tools.

These run against a live DB because the whole point of each tool is the
queryset it delegates to — mocking that away would leave nothing worth
asserting. Needs a live DB (integration tier).
"""

from __future__ import annotations

from account_v2.models import Organization, User
from api_v2.models import APIDeployment
from django.test import TestCase
from platform_api.models import PlatformApiKey
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from mcp_server.context import PlatformMCPContext
from mcp_server.tools.platform import (
    list_api_deployments,
    list_prompt_studio_projects,
    list_workflows,
    platform_read_me_first,
    whoami,
)

ORG_ID = "org-tools"


class PlatformToolsTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG_ID, display_name="Tools Org", organization_id=ORG_ID
        )
        UserContext.set_organization_identifier(ORG_ID)
        self.user = User.objects.create(
            username="svc-tools",
            email="svc-tools@platform.internal",
            user_id="uid-tools",
            is_service_account=True,
        )
        OrganizationMember.objects.create(
            user=self.user, organization=self.org, role="user"
        )
        self.key = PlatformApiKey.objects.create(
            name="tools-key",
            description="d",
            organization=self.org,
            api_user=self.user,
            permission="read_write",
        )

        self.workflow = Workflow.objects.create(
            workflow_name="invoice-wf", description="Invoices", is_active=True
        )
        self.api = APIDeployment.objects.create(
            api_name="invoice-api",
            display_name="Invoice API",
            description="Extracts invoices",
            workflow=self.workflow,
        )
        self.tool = CustomTool.objects.create(
            tool_name="Invoice Prompts", description="Prompt project", author="acme"
        )

        self.context = PlatformMCPContext(
            user=self.user, platform_key=self.key, org_name=ORG_ID
        )

    def test_list_api_deployments_exposes_the_api_name(self) -> None:
        """api_name is what an agent needs to open a deployment-scoped MCP
        session, so it must be in the payload — not just the display name.
        """
        result = list_api_deployments(self.context)

        assert result["count"] == 1
        row = result["api_deployments"][0]
        assert row["api_name"] == "invoice-api"
        assert row["display_name"] == "Invoice API"
        assert row["is_active"] is True
        assert "truncated" not in result

    def test_list_workflows_returns_the_org_workflow(self) -> None:
        result = list_workflows(self.context)

        assert result["count"] == 1
        assert result["workflows"][0]["workflow_name"] == "invoice-wf"

    def test_list_prompt_studio_projects_returns_the_org_project(self) -> None:
        result = list_prompt_studio_projects(self.context)

        assert result["count"] == 1
        assert result["prompt_studio_projects"][0]["tool_name"] == "Invoice Prompts"

    def test_listings_do_not_leak_across_organizations(self) -> None:
        """The single most important property of these tools. A platform key
        must never surface another tenant's resources.
        """
        other = Organization.objects.create(
            name="org-other", display_name="Other", organization_id="org-other"
        )
        UserContext.set_organization_identifier("org-other")
        other_wf = Workflow.objects.create(workflow_name="secret-wf", is_active=True)
        APIDeployment.objects.create(
            api_name="secret-api", display_name="Secret API", workflow=other_wf
        )
        CustomTool.objects.create(
            tool_name="Secret Prompts", description="d", author="other"
        )

        # Back to the original org: its key must see only its own resources.
        UserContext.set_organization_identifier(ORG_ID)

        names = [r["api_name"] for r in list_api_deployments(self.context)["api_deployments"]]
        assert names == ["invoice-api"]

        wf_names = [r["workflow_name"] for r in list_workflows(self.context)["workflows"]]
        assert "secret-wf" not in wf_names

        tool_names = [
            r["tool_name"]
            for r in list_prompt_studio_projects(self.context)["prompt_studio_projects"]
        ]
        assert "Secret Prompts" not in tool_names
        assert other.organization_id == "org-other"  # sanity: the other org exists

    def test_whoami_reports_tier_and_service_account_scope(self) -> None:
        """An agent that gets more results than a human would should be able to
        find out why.
        """
        result = whoami(self.context)

        assert result["organization"] == ORG_ID
        assert result["permission_tier"] == "read_write"
        assert result["is_service_account"] is True
        assert "read-only" in result["access"]

    def test_read_me_first_states_the_scope_warning(self) -> None:
        """The service-account visibility rule is surprising enough that the
        guide must say it outright, not leave it to be discovered.
        """
        result = platform_read_me_first(self.context)

        assert "service account" in result["scope_warning"].lower()
        assert result["organization"] == ORG_ID
        # It must also point at the other server, since this one cannot extract.
        assert "extractDocument" in result["to_run_an_extraction"]
