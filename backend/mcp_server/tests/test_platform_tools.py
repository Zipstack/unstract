"""Behaviour of the organization-scoped read-only tools.

These run against a live DB because the whole point of each tool is the
queryset it delegates to — mocking that away would leave nothing worth
asserting. Needs a live DB (integration tier).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import Mock, patch

from account_v2.models import Organization, User
from api_v2.models import APIDeployment
from django.test import TestCase
from pipeline_v2.models import Pipeline
from platform_api.models import PlatformApiKey
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from mcp_server.context import PlatformMCPContext
from mcp_server.exceptions import MCPToolError
from mcp_server.tools.platform_execution import (
    get_platform_execution_status,
    platform_extract_document,
)
from mcp_server.tools.platform import (
    execute_pipeline,
    list_api_deployments,
    list_prompt_studio_projects,
    list_workflows,
    platform_read_me_first,
    set_api_deployment_active,
    set_pipeline_active,
    whoami,
)
from mcp_server.tools.prompt_studio import (
    list_prompt_studio_documents,
    list_prompts,
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
        self.pipeline = Pipeline.objects.create(
            pipeline_name="etl-pipeline", workflow=self.workflow
        )

        self.context = PlatformMCPContext(
            user=self.user,
            platform_key=self.key,
            org_name=ORG_ID,
            request=Mock(data={}),
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
        # read_write may write but must not reach destructive tools.
        assert result["can_use_write_tools"] is True
        assert result["can_use_destructive_tools"] is False
        assert "modify" in result["visibility"]

    def test_set_api_deployment_active_toggles_and_reports_the_change(self) -> None:
        result = set_api_deployment_active(
            self.context, api_name="invoice-api", is_active=False
        )

        assert result["changed"] is True
        assert result["previous_state"] is True
        assert result["is_active"] is False
        self.api.refresh_from_db()
        assert self.api.is_active is False

    def test_set_api_deployment_active_is_a_noop_when_already_in_state(self) -> None:
        """Reporting `changed: False` rather than silently succeeding lets an
        agent tell "I did this" from "this was already so".
        """
        result = set_api_deployment_active(
            self.context, api_name="invoice-api", is_active=True
        )

        assert result["changed"] is False

    def test_set_api_deployment_active_rejects_an_unknown_name(self) -> None:
        with self.assertRaises(MCPToolError) as caught:
            set_api_deployment_active(
                self.context, api_name="no-such-api", is_active=False
            )

        # The message must point at the tool that lists valid names.
        assert "listApiDeployments" in str(caught.exception)

    def test_set_pipeline_active_toggles_the_schedule(self) -> None:
        result = set_pipeline_active(
            self.context, pipeline_id=str(self.pipeline.id), active=True
        )

        assert result["changed"] is True
        self.pipeline.refresh_from_db()
        assert self.pipeline.active is True

    def test_execute_pipeline_delegates_to_the_platform_manager(self) -> None:
        """Guards the tool-kwarg -> PipelineManager mapping.

        Nothing else executes this call, so a renamed kwarg would pass every
        other test and fail on the first real pipeline run.
        """
        fake_response = Mock(status_code=200, data={"execution": "started"})
        with patch(
            "pipeline_v2.manager.PipelineManager.execute_pipeline",
            return_value=fake_response,
        ) as execute:
            result = execute_pipeline(self.context, pipeline_id=str(self.pipeline.id))

        execute.assert_called_once_with(
            request=self.context.request, pipeline_id=str(self.pipeline.id)
        )
        assert result["status"] == 200
        assert result["pipeline_name"] == "etl-pipeline"

    def test_execute_pipeline_rejects_an_unknown_id(self) -> None:
        with patch("pipeline_v2.manager.PipelineManager.execute_pipeline") as execute:
            with self.assertRaises(MCPToolError):
                execute_pipeline(
                    self.context, pipeline_id="99999999-9999-9999-9999-999999999999"
                )

        execute.assert_not_called()

    def test_writes_do_not_cross_organizations(self) -> None:
        """The most important property of the write tools.

        A platform key must not be able to deactivate, pause or run another
        tenant's resources — the read-side isolation test has a write-side
        equivalent because the consequences here are not merely disclosure.
        """
        UserContext.set_organization_identifier("org-write-other")
        Organization.objects.create(
            name="org-write-other",
            display_name="Other",
            organization_id="org-write-other",
        )
        other_wf = Workflow.objects.create(workflow_name="other-wf", is_active=True)
        other_api = APIDeployment.objects.create(
            api_name="other-api", display_name="Other API", workflow=other_wf
        )
        other_pipeline = Pipeline.objects.create(
            pipeline_name="other-pipeline", workflow=other_wf
        )

        UserContext.set_organization_identifier(ORG_ID)

        with self.assertRaises(MCPToolError):
            set_api_deployment_active(
                self.context, api_name="other-api", is_active=False
            )
        with self.assertRaises(MCPToolError):
            set_pipeline_active(
                self.context, pipeline_id=str(other_pipeline.id), active=True
            )
        with patch("pipeline_v2.manager.PipelineManager.execute_pipeline") as execute:
            with self.assertRaises(MCPToolError):
                execute_pipeline(self.context, pipeline_id=str(other_pipeline.id))
            execute.assert_not_called()

        # And nothing was touched.
        other_api.refresh_from_db()
        other_pipeline.refresh_from_db()
        assert other_api.is_active is True
        assert other_pipeline.active is False

    def test_read_me_first_states_the_scope_warning(self) -> None:
        """The service-account visibility rule is surprising enough that the
        guide must say it outright, not leave it to be discovered.
        """
        result = platform_read_me_first(self.context)

        assert "service account" in result["scope_warning"].lower()
        assert result["organization"] == ORG_ID
        # It must also point at the other server, since this one cannot extract.
        assert "extractDocument" in result["to_run_an_extraction"]


class PromptStudioProducerToolsTest(TestCase):
    """The two tools that make the billable Prompt Studio tools reachable.

    ``indexDocument``, ``fetchResponse``, ``bulkFetchResponse`` and
    ``singlePassExtraction`` all require ids an agent has no way to invent.
    These tools are the only source of them, so their payload shape is load
    bearing in a way a listing's usually is not — a missing ``document_id``
    field here silently disables every billable tool on the server.
    """

    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-producers",
            display_name="Producers Org",
            organization_id="org-producers",
        )
        UserContext.set_organization_identifier("org-producers")
        self.user = User.objects.create(
            username="svc-producers",
            email="svc-producers@platform.internal",
            user_id="uid-producers",
            is_service_account=True,
        )
        OrganizationMember.objects.create(
            user=self.user, organization=self.org, role="user"
        )
        self.key = PlatformApiKey.objects.create(
            name="producers-key",
            description="d",
            organization=self.org,
            api_user=self.user,
            permission="read_write",
        )
        self.project = CustomTool.objects.create(
            tool_name="Invoice Prompts", description="Prompt project", author="acme"
        )
        self.document = DocumentManager.objects.create(
            document_name="invoice-001.pdf", tool=self.project
        )
        self.prompt = ToolStudioPrompt.objects.create(
            prompt_key="invoice_number",
            prompt="What is the invoice number?",
            tool_id=self.project,
            sequence_number=1,
            prompt_type="Text",
            enforce_type="text",
            # Set deliberately: the redaction assertion below is only meaningful
            # if there is a webhook URL that *could* have leaked.
            postprocessing_webhook_url="https://hooks.internal/acme?token=s3cr3t",
        )
        self.context = PlatformMCPContext(
            user=self.user,
            platform_key=self.key,
            org_name="org-producers",
            request=Mock(data={}),
        )

    def test_documents_are_listed_with_the_id_billable_tools_need(self) -> None:
        result = list_prompt_studio_documents(
            self.context, project_id=str(self.project.tool_id)
        )

        assert result["documents"] == [
            {
                "document_id": str(self.document.document_id),
                "document_name": "invoice-001.pdf",
            }
        ]

    def test_prompts_are_listed_with_the_id_fetch_response_needs(self) -> None:
        result = list_prompts(self.context, project_id=str(self.project.tool_id))

        assert len(result["prompts"]) == 1
        row = result["prompts"][0]
        assert row["prompt_id"] == str(self.prompt.prompt_id)
        assert row["prompt_key"] == "invoice_number"
        assert row["prompt"] == "What is the invoice number?"

    def test_listing_prompts_does_not_leak_adapters_or_webhooks(self) -> None:
        """The promise the README makes, pinned.

        ``ToolStudioPrompt`` carries a ``profile_manager`` FK — the LLM,
        embedding and vector-store adapters behind the prompt — and a
        webhook URL that may embed a token. A serializer would have carried
        both out to the agent, which is why the handler builds its dict by
        hand. This test is what stops someone swapping it back.
        """
        result = list_prompts(self.context, project_id=str(self.project.tool_id))

        payload = json.dumps(result)
        assert "profile_manager" not in payload
        assert "postprocessing_webhook_url" not in payload
        assert "s3cr3t" not in payload, "a webhook token reached the agent"
        assert "hooks.internal" not in payload

    def test_an_unknown_project_is_refused_with_a_usable_message(self) -> None:
        with self.assertRaises(MCPToolError) as caught:
            list_prompts(self.context, project_id="00000000-0000-0000-0000-000000000000")

        assert "listPromptStudioProjects" in str(caught.exception)

    def test_documents_do_not_leak_across_projects(self) -> None:
        """Documents are resolved through the project, never by a bare id
        lookup. The platform key is a service account, for which ``for_user``
        returns everything, so the project join is the scoping that holds.
        """
        other = CustomTool.objects.create(
            tool_name="Other Project", description="d", author="acme"
        )
        DocumentManager.objects.create(document_name="secret.pdf", tool=other)

        result = list_prompt_studio_documents(
            self.context, project_id=str(self.project.tool_id)
        )

        names = [row["document_name"] for row in result["documents"]]
        assert names == ["invoice-001.pdf"], "a sibling project's document leaked"


class PlatformExtractionScopeTest(TestCase):
    """The organization boundary on platform-side extraction.

    On the deployment server the API key narrowed a caller to one deployment,
    so an execution id from elsewhere was unreachable by construction. Nothing
    narrows a platform caller, and ``get_status_of_async_task`` resolves a bare
    ``WorkflowExecution.objects.get(id=...)`` with no tenant filter — this
    deployment runs one shared schema (``TENANT_APPS`` is empty), so there is
    no per-tenant database to fall back on. These tests pin the check that
    replaces the one the credential used to provide.
    """

    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-extract",
            display_name="Extract Org",
            organization_id="org-extract",
        )
        UserContext.set_organization_identifier("org-extract")
        self.user = User.objects.create(
            username="svc-extract",
            email="svc-extract@platform.internal",
            user_id="uid-extract",
            is_service_account=True,
        )
        OrganizationMember.objects.create(
            user=self.user, organization=self.org, role="user"
        )
        self.key = PlatformApiKey.objects.create(
            name="extract-key",
            description="d",
            organization=self.org,
            api_user=self.user,
            permission="read_write",
        )
        self.workflow = Workflow.objects.create(
            workflow_name="extract-wf", is_active=True
        )
        self.api = APIDeployment.objects.create(
            api_name="extract-api", display_name="Extract API", workflow=self.workflow
        )
        self.context = PlatformMCPContext(
            user=self.user,
            platform_key=self.key,
            org_name="org-extract",
            request=Mock(data={}),
        )

    def _execution_for(self, workflow) -> Any:
        with patch(
            "workflow_manager.workflow_v2.models.execution."
            "WorkflowExecution._handle_execution_cache"
        ):
            return WorkflowExecution.objects.create(
                workflow_id=workflow.id, status="PENDING"
            )

    def test_another_organizations_execution_is_not_readable(self) -> None:
        """The boundary this change actually creates. A platform key must not
        be able to poll an execution belonging to another tenant.
        """
        UserContext.set_organization_identifier("org-extract-other")
        Organization.objects.create(
            name="org-extract-other",
            display_name="Other",
            organization_id="org-extract-other",
        )
        other_wf = Workflow.objects.create(workflow_name="other-wf", is_active=True)
        APIDeployment.objects.create(
            api_name="other-api", display_name="Other API", workflow=other_wf
        )
        foreign = self._execution_for(other_wf)

        UserContext.set_organization_identifier("org-extract")

        with self.assertRaises(MCPToolError) as caught:
            get_platform_execution_status(self.context, execution_id=str(foreign.id))

        # The message must not confirm the id exists elsewhere.
        assert "org-extract-other" not in str(caught.exception)

    def test_an_unknown_execution_is_refused(self) -> None:
        with self.assertRaises(MCPToolError):
            get_platform_execution_status(
                self.context, execution_id="00000000-0000-0000-0000-000000000000"
            )

    def test_a_pipeline_run_is_refused_with_a_pointer_to_the_right_tool(self) -> None:
        """The second gate. A workflow in this org that is not behind an API
        deployment has no deployment to build a context from, so it must be
        refused rather than fail deeper with an unhelpful error.
        """
        pipeline_wf = Workflow.objects.create(
            workflow_name="pipeline-only-wf", is_active=True
        )
        execution = self._execution_for(pipeline_wf)

        with self.assertRaises(MCPToolError) as caught:
            get_platform_execution_status(self.context, execution_id=str(execution.id))

        assert "getExecutionDetail" in str(caught.exception)

    def test_extraction_refuses_a_deployment_outside_the_organization(self) -> None:
        UserContext.set_organization_identifier("org-extract-far")
        Organization.objects.create(
            name="org-extract-far",
            display_name="Far",
            organization_id="org-extract-far",
        )
        far_wf = Workflow.objects.create(workflow_name="far-wf", is_active=True)
        APIDeployment.objects.create(
            api_name="far-api", display_name="Far API", workflow=far_wf
        )

        UserContext.set_organization_identifier("org-extract")

        with self.assertRaises(MCPToolError) as caught:
            platform_extract_document(
                self.context,
                api_name="far-api",
                document_urls=["https://s3.example.com/doc.pdf?X-Amz-Signature=x"],
            )

        assert "listApiDeployments" in str(caught.exception)
