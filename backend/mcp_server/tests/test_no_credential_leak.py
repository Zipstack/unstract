"""Registry-wide invariant: no tool output may contain a credential.

This is the test that keeps the README's exclusion list true as tools get
added. Several of this project's serializers return decrypted secrets in their
normal responses — ``ConnectorInstance.connector_metadata`` carries database
passwords and object-store keys, ``AdapterInstance.metadata`` carries provider
API keys — so a tool that reaches a model through ``serializer.data``,
``model_to_dict`` or a ``**`` splat would pipe those into an LLM's context
without anyone noticing at review time.

Rather than trusting each tool to be written carefully, this seeds an
organization with recognizable fake secrets, invokes **every** read tool in the
platform registry, and asserts none of those strings comes back. A new tool is
covered the moment it is registered.

Needs a live DB (integration tier).
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest
from account_v2.models import Organization, User
from adapter_processor_v2.models import AdapterInstance
from api_v2.models import APIDeployment
from connector_v2.models import ConnectorInstance
from django.test import TestCase, override_settings
from platform_api.models import PlatformApiKey
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from mcp_server.context import PlatformMCPContext
from mcp_server.registry import PLATFORM_TOOLS

ORG_ID = "org-leak"

# `whoami` reports the spend budget, which reads the cache. Use local memory so
# this test exercises tool output rather than Redis availability.
LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mcp-leak-tests",
    }
}

# Distinctive sentinels: if any of these appears in tool output, a secret
# escaped. Chosen not to collide with anything a tool would legitimately emit.
DB_PASSWORD = "LEAKCANARY-db-password-9f3a"
S3_SECRET = "LEAKCANARY-s3-secret-key-7c1b"
LLM_API_KEY = "LEAKCANARY-openai-api-key-4e8d"

# Only secrets are canaries. A platform key's *name* is deliberately surfaced
# by whoami — it is a label the operator chose, not credential material, and
# treating it as one would make this test object to correct behaviour.
CANARIES = (DB_PASSWORD, S3_SECRET, LLM_API_KEY)


@override_settings(CACHES=LOCMEM)
class NoCredentialLeakTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG_ID, display_name="Leak Org", organization_id=ORG_ID
        )
        UserContext.set_organization_identifier(ORG_ID)
        self.user = User.objects.create(
            username="svc-leak",
            email="svc-leak@platform.internal",
            user_id="uid-leak",
            is_service_account=True,
        )
        OrganizationMember.objects.create(
            user=self.user, organization=self.org, role="user"
        )
        self.key = PlatformApiKey.objects.create(
            name="leak-test-key",
            description="d",
            organization=self.org,
            api_user=self.user,
            permission="read_write",
        )

        # A connector holding credentials, wired into a workflow endpoint —
        # the transitive path that makes getWorkflowEndpoints risky.
        self.connector = ConnectorInstance.objects.create(
            connector_name="Leak Postgres",
            connector_id="postgresql|4d3a1b0e-1f2c-4a3d-9e8f-0a1b2c3d4e5f",
            connector_metadata={
                "user": "admin",
                "password": DB_PASSWORD,
                "secret_access_key": S3_SECRET,
            },
        )
        # `adapter_metadata` is the writable field; `metadata` is the property
        # that decrypts it on read — which is exactly why a tool must never
        # serialize this model wholesale.
        self.adapter = AdapterInstance.objects.create(
            adapter_name="Leak LLM",
            adapter_id="openai|1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
            adapter_type="LLM",
            adapter_metadata={"api_key": LLM_API_KEY},
        )

        self.workflow = Workflow.objects.create(
            workflow_name="leak-wf", description="d", is_active=True
        )
        WorkflowEndpoint.objects.create(
            workflow=self.workflow,
            endpoint_type=WorkflowEndpoint.EndpointType.SOURCE,
            connection_type=WorkflowEndpoint.ConnectionType.DATABASE,
            connector_instance=self.connector,
            configuration={"table": "docs", "password_hint": DB_PASSWORD},
        )
        APIDeployment.objects.create(
            api_name="leak-api", display_name="Leak API", workflow=self.workflow
        )
        self.project = CustomTool.objects.create(
            tool_name="Leak Prompts", description="d", author="acme"
        )
        DocumentManager.objects.create(
            document_name="leak-doc.pdf", tool=self.project
        )
        # The webhook URL carries a canary because ToolStudioPrompt is the one
        # model in this sweep with a credential-bearing field that is not a
        # connector or adapter — a serializer-built response would carry it
        # straight out, and this is what catches that.
        ToolStudioPrompt.objects.create(
            prompt_key="leak_check",
            prompt="What is the total?",
            tool_id=self.project,
            sequence_number=1,
            prompt_type="Text",
            enforce_type="text",
            postprocessing_webhook_url=f"https://hooks.internal/x?token={LLM_API_KEY}",
        )
        # WorkflowExecution.save() mirrors into a Redis-backed execution cache
        # via its own client, which override_settings(CACHES=...) does not
        # cover. That mirroring is irrelevant here — the tool reads the DB —
        # so it is stubbed to keep this test off live infra.
        with patch(
            "workflow_manager.workflow_v2.models.execution."
            "WorkflowExecution._handle_execution_cache"
        ):
            self.execution = WorkflowExecution.objects.create(
                workflow_id=self.workflow.id,
                status="ERROR",
                # Error text is echoed back to the agent, so seed a canary
                # here too: a stack trace is where a connection string leaks.
                error_message=f"connect failed: password={DB_PASSWORD}",
            )

        self.context = PlatformMCPContext(
            user=self.user,
            platform_key=self.key,
            org_name=ORG_ID,
            request=Mock(data={}),
        )

    def _read_tools(self):
        """Every non-billable, non-writing tool — the ones safe to just call."""
        for name in PLATFORM_TOOLS.names():
            tool = PLATFORM_TOOLS.get(name)
            if tool.writes or tool.billable:
                continue
            yield name, tool

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_no_read_tool_returns_a_credential(self) -> None:
        """Invoke every read tool and scan its output for the canaries.

        Tools needing an argument get the seeded ids; anything that still
        cannot be called is reported rather than silently skipped, so this
        cannot quietly stop covering the registry.
        """
        arguments = {
            "getWorkflowEndpoints": {"workflow_id": str(self.workflow.id)},
            "listToolInstances": {"workflow_id": str(self.workflow.id)},
            "listExecutions": {},
            "getUsageSummary": {},
            "getExecutionDetail": {"execution_id": str(self.execution.id)},
            "listPromptStudioDocuments": {"project_id": str(self.project.tool_id)},
            "listPrompts": {"project_id": str(self.project.tool_id)},
        }

        checked = []
        for name, tool in self._read_tools():
            kwargs = arguments.get(name, {})
            required = tool.input_schema.get("required", [])
            if any(field not in kwargs for field in required):
                # A read tool needing arguments this test does not know how to
                # supply. Fail loudly: an uncovered tool is the whole risk.
                raise AssertionError(
                    f"Read tool '{name}' requires {required} but this test has "
                    f"no fixture for it — add one so it stays covered."
                )

            result = tool.handler(self.context, **kwargs)
            blob = json.dumps(result, default=str)
            checked.append(name)

            for canary in CANARIES:
                assert canary not in blob, (
                    f"Tool '{name}' leaked a credential ({canary}). Build its "
                    f"response from named fields — never serializer.data, "
                    f"model_to_dict, or a ** splat."
                )

        # Guard the guard: if the filter above ever matches nothing, this test
        # would pass vacuously.
        assert len(checked) >= 5, f"Expected to check several tools, got {checked}"

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_workflow_endpoints_omits_connector_configuration(self) -> None:
        """The specific transitive path worth naming.

        A workflow endpoint points at a connector instance whose metadata is
        decrypted on access. Returning the endpoint's own `configuration`, or
        following the relation into the connector, would leak it.
        """
        from mcp_server.tools.observability import get_workflow_endpoints

        result = get_workflow_endpoints(self.context, workflow_id=str(self.workflow.id))
        blob = json.dumps(result, default=str)

        assert result["endpoints"], "fixture should produce one endpoint"
        endpoint = result["endpoints"][0]
        # The shape is exposed...
        assert endpoint["connection_type"] == "DATABASE"
        assert endpoint["connector_name"] == "Leak Postgres"
        assert endpoint["is_configured"] is True
        # ...but never the contents.
        assert "configuration" not in endpoint
        assert "connector_metadata" not in blob
        assert DB_PASSWORD not in blob

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_no_tool_wraps_connectors_or_adapters(self) -> None:
        """These subsystems are excluded wholesale, not filtered.

        Their serializers return decrypted credentials by design, so the safe
        boundary is to expose no tool for them at all rather than to trust a
        field-level filter to stay correct.
        """
        forbidden = ("connector", "adapter")
        offenders = [
            name
            for name in PLATFORM_TOOLS.names()
            if any(word in name.lower() for word in forbidden)
        ]

        assert offenders == [], (
            f"Connector and adapter responses carry decrypted credentials; "
            f"no MCP tool should wrap them: {offenders}"
        )
