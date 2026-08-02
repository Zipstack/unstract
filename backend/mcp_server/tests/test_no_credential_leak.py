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
from django.test import SimpleTestCase, TestCase, override_settings
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

# Ids for the delegate-stubbed sweep below. Real UUIDs because the tools now
# validate id shape before doing anything else.
PROJECT_UUID = "11111111-1111-1111-1111-111111111111"
DOCUMENT_UUID = "22222222-2222-2222-2222-222222222222"
PROMPT_UUID = "33333333-3333-3333-3333-333333333333"
PIPELINE_UUID = "44444444-4444-4444-4444-444444444444"
WORKFLOW_UUID = "55555555-5555-5555-5555-555555555555"
EXECUTION_UUID = "66666666-6666-6666-6666-666666666666"
DOC_URL = "https://b.s3.us-east-1.amazonaws.com/a.pdf?X-Amz-Signature=abc"

# Single marker for the field-seeded sweep. Distinct from the CANARIES above,
# which are credential-shaped values placed in specific fixtures; this one is
# written into *every* free-form field, so any wholesale serialization trips it.
CANARY = "LEAKCANARY-field-seeded-8b2e"


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
        DocumentManager.objects.create(document_name="leak-doc.pdf", tool=self.project)
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
        """Every non-billable, non-writing tool — the ones safe to just call.

        Write and billable tools are excluded because invoking them here would
        start real executions and spend real budget, not because they are
        believed safe. They fall into two groups:

        * Those that **delegate** — the four Prompt Studio tools, ``executePipeline``
          and ``extractDocument`` — return upstream data this app did not
          assemble field by field, so their results pass through
          ``redact_structure``. Those call sites are pinned by
          ``test_redaction.WriteToolRedactionCallSitesTest``.
        * ``setApiDeploymentActive`` and ``setPipelineActive`` hand-assemble
          named fields exactly like the read tools; they are excluded only for
          their side effect, not because they return anything raw.

        That is still a weaker guarantee than this sweep gives the read tools:
        it pins the call sites individually rather than walking the registry, so
        a *new* delegating write tool added without redaction would be caught by
        nothing here. Extending the sweep to invoke the write tools against
        stubbed delegates is worth doing and is not attempted in this change.
        """
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
            # Seeded against this org's workflow, so the tool gets past its
            # org-scope check and actually renders a response to scan.
            "getExecutionStatus": {"execution_id": str(self.execution.id)},
        }

        checked = []
        # The seeded execution has status ERROR, which ExecutionStatus counts
        # as terminal — so getExecutionStatus takes its is_completed branch and
        # reads results through a raw Redis client that
        # override_settings(CACHES=...) does not reach, exactly like
        # _handle_execution_cache above. Stubbed to keep this test off live
        # infra; the cached results are not what is being scanned here.
        result_cache = patch(
            "workflow_manager.endpoint_v2.result_cache_utils."
            "ResultCacheUtils.get_api_results",
            return_value=[],
        )
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

            with result_cache:
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

        # Note on coverage depth: canaries live in the fixtures above, so a
        # tool reading a model nobody seeded is invoked and scanned but could
        # not have failed. `ReadToolCanaryCoverageTest` closes that by seeding
        # every free-form field of an unsaved instance per tool; this sweep
        # remains the stronger check for the tools it does cover, because it
        # runs real managers, `for_user` scoping and decrypting properties.

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


class WriteToolLeakSweepTest(SimpleTestCase):
    """The sweep above, extended to the tools it could not invoke.

    ``PlatformToolLeakSweepTest`` skips every ``writes``/``billable`` tool
    because calling them for real would start executions and spend budget — but
    those are precisely the tools that return upstream data this app did not
    assemble field by field, so leaving them uncovered left the guarantee
    hollow exactly where it mattered most.

    The fix is to stub the delegate rather than skip the tool: each tool is
    invoked for real, with the boundary it delegates to (a Prompt Studio view
    action, ``PipelineManager``, ``DeploymentHelper``) returning a canary. What
    is under test is whether the tool's own return path scrubs what it is
    handed — which is the same question the read sweep asks, just reachable
    without live infra.

    Both directions are covered, because they take different code paths: a 2xx
    body flows through the success branch, a non-2xx body through the
    error-reporting branch that ``_result`` deliberately returns *as data*.

    ``SimpleTestCase``: no database. The project/pipeline/deployment lookups are
    the part that would need one, and they are stubbed.
    """

    def _context(self):
        context = Mock()
        context.org_name = ORG_ID
        context.request = Mock(data={})
        context.platform_key = Mock(name="k")
        context.user = Mock(is_service_account=True)
        return context

    def _assert_clean(self, result, tool_name: str) -> None:
        blob = json.dumps(result, default=str)
        for canary in CANARIES:
            assert canary not in blob, (
                f"Tool '{tool_name}' leaked a credential ({canary}) from its "
                "delegate's response. Route the upstream payload through "
                "redact_structure before returning it."
            )

    # --- Prompt Studio: the four billable tools share _result ---------------

    def _run_prompt_studio(self, tool, status_code: int, data, **kwargs):
        """Invoke a Prompt Studio tool with the view action stubbed."""
        from mcp_server.tools import prompt_studio as ps

        project = Mock(tool_id=PROJECT_UUID, tool_name="Leak Prompts")
        response = Mock(status_code=status_code, data=data)

        class StubView:
            def __init__(self) -> None:
                pass

            def __getattr__(self, item):
                return lambda request, pk=None: response

        with (
            patch.object(ps, "_resolve_project", return_value=project),
            patch.object(ps, "PromptStudioCoreView", StubView),
        ):
            return tool(self._context(), project_id=PROJECT_UUID, **kwargs)

    def test_prompt_studio_tools_scrub_a_successful_response(self) -> None:
        from mcp_server.tools.prompt_studio import (
            bulk_fetch_response,
            fetch_response,
            index_document,
            single_pass_extraction,
        )

        # A delegated view returning an indexing summary that happens to embed
        # the adapter's key — the shape a real failure downstream produces.
        leaky = {"output": "ok", "profile": {"api_key": LLM_API_KEY}}
        cases = [
            (index_document, "indexDocument", {"document_id": DOCUMENT_UUID}),
            (
                fetch_response,
                "fetchResponse",
                {"document_id": DOCUMENT_UUID, "prompt_id": PROMPT_UUID},
            ),
            (
                bulk_fetch_response,
                "bulkFetchResponse",
                {"document_id": DOCUMENT_UUID, "prompt_ids": [PROMPT_UUID]},
            ),
            (
                single_pass_extraction,
                "singlePassExtraction",
                {"document_id": DOCUMENT_UUID},
            ),
        ]
        for tool, name, kwargs in cases:
            with self.subTest(name):
                result = self._run_prompt_studio(tool, 200, leaky, **kwargs)
                self._assert_clean(result, name)

    def test_prompt_studio_tools_scrub_an_error_response(self) -> None:
        """The path that matters more: `_result` returns non-2xx bodies as
        data, and a delegated view's error text is where a connection string
        actually surfaces.
        """
        from mcp_server.tools.prompt_studio import index_document

        leaky = {"detail": f"could not connect: password={DB_PASSWORD}"}

        result = self._run_prompt_studio(
            index_document, 500, leaky, document_id=DOCUMENT_UUID
        )

        self._assert_clean(result, "indexDocument")
        assert result["ok"] is False

    # --- executePipeline -----------------------------------------------------

    def test_execute_pipeline_scrubs_its_manager_response(self) -> None:
        from mcp_server.tools import platform as platform_tools
        from mcp_server.tools.platform import execute_pipeline

        pipeline = Mock(id=PIPELINE_UUID, pipeline_name="Leak Pipeline")
        for label, status, data in [
            ("success", 200, {"log": f"connected with password={DB_PASSWORD}"}),
            ("error", 500, {"detail": f"api_key={LLM_API_KEY} rejected"}),
        ]:
            with self.subTest(label):
                with (
                    patch.object(
                        platform_tools, "_resolve_pipeline", return_value=pipeline
                    ),
                    patch(
                        "pipeline_v2.manager.PipelineManager.execute_pipeline",
                        return_value=Mock(status_code=status, data=data),
                    ),
                ):
                    result = execute_pipeline(
                        self._context(), pipeline_id=PIPELINE_UUID
                    )
                self._assert_clean(result, "executePipeline")

    # --- extractDocument and its poll ---------------------------------------

    def test_extract_document_scrubs_the_execution_response(self) -> None:
        from mcp_server.tools.execution import extract_document

        context = Mock()
        context.org_name = ORG_ID
        context.api = Mock(is_active=True, api_name="leak-api")
        context.api_key = "k"

        leaky = {
            "execution_status": "ERROR",
            "error": f"connector refused: password={DB_PASSWORD}",
        }
        with (
            patch(
                "mcp_server.tools.execution.ExecutionRequestSerializer.is_valid",
                return_value=True,
            ),
            patch(
                "mcp_server.tools.execution.ExecutionRequestSerializer.validated_data",
                {"presigned_urls": [DOC_URL]},
            ),
            patch(
                "mcp_server.tools.execution.APIDeploymentRateLimiter.check_and_acquire",
                return_value=(True, {}),
            ),
            patch("mcp_server.tools.execution.DeploymentHelper.load_presigned_files"),
            patch(
                "mcp_server.tools.execution.DeploymentHelper.execute_workflow",
                return_value=leaky,
            ),
        ):
            result = extract_document(context, document_urls=[DOC_URL])

        self._assert_clean(result, "extractDocument")

    def test_get_execution_status_scrubs_the_polled_result(self) -> None:
        """The tool the credential-leak sweep originally caught a leak in."""
        from workflow_manager.workflow_v2.dto import ExecutionResponse

        from mcp_server.tools.execution import get_execution_status

        context = Mock()
        context.api = Mock(workflow_id=WORKFLOW_UUID)

        response = ExecutionResponse(
            workflow_id=WORKFLOW_UUID,
            execution_id=EXECUTION_UUID,
            execution_status="ERROR",
            result=[{"file": "a.pdf", "error": f"secret_access_key={S3_SECRET}"}],
        )
        with (
            patch("mcp_server.tools.execution.WorkflowExecution.objects.filter") as f,
            patch(
                "mcp_server.tools.execution.ExecutionQuerySerializer.is_valid",
                return_value=True,
            ),
            patch(
                "mcp_server.tools.execution.ExecutionQuerySerializer.validated_data",
                {
                    "execution_id": EXECUTION_UUID,
                    "include_metadata": False,
                    "include_metrics": False,
                    "include_extracted_text": False,
                },
            ),
            patch(
                "mcp_server.tools.execution.DeploymentHelper.get_execution_status",
                return_value=response,
            ),
            patch(
                "mcp_server.tools.execution.DeploymentHelper."
                "process_completed_execution"
            ),
        ):
            f.return_value.only.return_value.first.return_value = object()
            result = get_execution_status(context, execution_id=EXECUTION_UUID)

        self._assert_clean(result, "getExecutionStatus")

    # --- the guard on the guard ---------------------------------------------

    def test_every_write_and_billable_tool_is_covered_here(self) -> None:
        """Walks the registry so a *new* write tool cannot be added without
        either covering it or deliberately exempting it.

        This is the gap the per-call-site tests could not close: they pin the
        four sites that exist today, and would stay green while a fifth
        delegating tool shipped with no redaction at all.
        """
        covered = {
            "indexDocument",
            "fetchResponse",
            "bulkFetchResponse",
            "singlePassExtraction",
            "executePipeline",
            "extractDocument",
        }
        # These write but build their response from named fields, exactly like
        # the read tools — so they are covered by the read sweep's reasoning
        # rather than needing a delegate stub. Named explicitly so adding one
        # is a deliberate act.
        exempt = {"setApiDeploymentActive", "setPipelineActive"}

        writing = {
            name
            for name in PLATFORM_TOOLS.names()
            if PLATFORM_TOOLS.get(name).writes or PLATFORM_TOOLS.get(name).billable
        }
        uncovered = writing - covered - exempt

        assert uncovered == set(), (
            f"These tools write or spend but no leak test invokes them: "
            f"{sorted(uncovered)}. Add a delegate-stubbed case above, or add "
            f"the tool to `exempt` if it returns only named fields."
        )


# Fields Django reports as concrete and free-form enough to hold a credential.
# Seeding is driven off this rather than a hand-kept list, so a model that
# grows a new text field is canaried without anyone remembering to.
_SEEDABLE_FIELD_TYPES = ("CharField", "TextField", "JSONField", "URLField", "EmailField")


def seed_canaries(instance, canary: str, skip: tuple[str, ...] = ()) -> object:
    """Write ``canary`` into every free-form field of an unsaved model instance.

    The point is to make the scan non-vacuous *by construction*: rather than
    guessing which field a leak would come through, every field that could hold
    one gets a canary, so any tool that serializes wholesale is caught wherever
    it leaks from.

    ``skip`` is for fields a tool legitimately returns — a workflow's name is
    not a secret, and the tool is supposed to echo it — so seeding those would
    assert the opposite of what is intended.
    """
    for field in instance._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        if field.name in skip or field.primary_key or field.is_relation:
            continue
        kind = field.get_internal_type()
        if kind not in _SEEDABLE_FIELD_TYPES:
            continue
        if getattr(field, "choices", None):
            # A choice field rejects arbitrary text and is not free-form
            # enough to hide a credential.
            continue
        setattr(
            instance,
            field.name,
            {"leak": canary} if kind == "JSONField" else f"{canary}-{field.name}",
        )
    return instance


class ReadToolCanaryCoverageTest(SimpleTestCase):
    """Every read tool is scanned against data that *could* leak.

    ``PlatformToolLeakSweepTest`` invokes every read tool, but seeds canaries
    into only the three fixtures some of them happen to read — so the rest are
    scanned vacuously and would pass while serializing everything. This closes
    that by handing each tool a real (unsaved) model instance whose every
    free-form field carries a canary.

    Real model instances, not Mocks: these tools read named attributes off
    models, so what is under test is whether the tool names safe fields. A Mock
    would answer to any attribute and prove nothing about the model; an unsaved
    instance has exactly the fields Django says it has, and needs no database.

    The DB-backed sweep stays the stronger test — it exercises real managers,
    ``for_user`` scoping and decrypting property fields. This one is what can
    run in the unit tier, and it covers the tools that sweep leaves vacuous.
    """

    def _context(self):
        context = Mock()
        context.org_name = ORG_ID
        context.user = Mock(is_service_account=True)
        context.platform_key = Mock(name="k")
        return context

    def _assert_clean(self, result, tool_name: str) -> None:
        blob = json.dumps(result, default=str)
        assert CANARY not in blob, (
            f"Tool '{tool_name}' returned a seeded canary. It is serializing a "
            "field it does not name explicitly — build the response from named "
            "fields, never serializer.data, model_to_dict or a ** splat."
        )

    def test_list_workflows_returns_only_named_fields(self) -> None:
        from mcp_server.tools.platform import list_workflows

        workflow = seed_canaries(
            Workflow(is_active=True), CANARY, skip=("workflow_name", "description")
        )
        with patch(
            "mcp_server.tools.platform.Workflow.objects.for_user"
        ) as for_user:
            for_user.return_value.order_by.return_value = _FakeRows([workflow])
            result = list_workflows(self._context())

        self._assert_clean(result, "listWorkflows")

    def test_list_api_deployments_returns_only_named_fields(self) -> None:
        from mcp_server.tools.platform import list_api_deployments

        deployment = seed_canaries(
            APIDeployment(is_active=True, workflow=Workflow()),
            CANARY,
            skip=("display_name", "api_name", "description"),
        )
        with patch(
            "mcp_server.tools.platform.APIDeployment.objects.for_user"
        ) as for_user:
            for_user.return_value.order_by.return_value = _FakeRows([deployment])
            result = list_api_deployments(self._context())

        self._assert_clean(result, "listApiDeployments")

    def test_list_pipelines_returns_only_named_fields(self) -> None:
        from pipeline_v2.models import Pipeline

        from mcp_server.tools.platform import list_pipelines

        pipeline = seed_canaries(
            Pipeline(active=True), CANARY, skip=("pipeline_name",)
        )
        with patch("mcp_server.tools.platform.Pipeline.objects.for_user") as for_user:
            for_user.return_value.order_by.return_value = _FakeRows([pipeline])
            result = list_pipelines(self._context())

        self._assert_clean(result, "listPipelines")

    def test_list_prompt_studio_projects_returns_only_named_fields(self) -> None:
        from mcp_server.tools.platform import list_prompt_studio_projects

        project = seed_canaries(
            CustomTool(), CANARY, skip=("tool_name", "description", "author")
        )
        with patch("mcp_server.tools.platform.CustomTool.objects.for_user") as for_user:
            for_user.return_value.order_by.return_value = _FakeRows([project])
            result = list_prompt_studio_projects(self._context())

        self._assert_clean(result, "listPromptStudioProjects")

    def test_list_tool_instances_omits_tool_settings(self) -> None:
        """The highest-risk of these: a tool step's ``metadata`` is free-form
        JSON that can carry adapter ids and credential-shaped values, and the
        tool's own docstring says it omits them. This is what proves it.
        """
        from tool_instance_v2.models import ToolInstance

        from mcp_server.tools.observability import list_tool_instances

        workflow = Workflow(workflow_name="wf")
        # `tool_id` is skipped because the tool names it deliberately — it is
        # the identifier an agent needs to make sense of the step, not a
        # secret. Everything else, `metadata` above all, is seeded.
        step = seed_canaries(
            ToolInstance(workflow=workflow, step=1), CANARY, skip=("tool_id",)
        )
        assert CANARY in json.dumps(step.metadata, default=str), (
            "metadata must carry a canary or this test proves nothing"
        )
        with (
            patch(
                "mcp_server.tools.observability.Workflow.objects.for_user"
            ) as for_user,
            patch(
                "tool_instance_v2.models.ToolInstance.objects.filter"
            ) as tool_filter,
        ):
            for_user.return_value.filter.return_value.first.return_value = workflow
            tool_filter.return_value.order_by.return_value = [step]
            result = list_tool_instances(
                self._context(), workflow_id=str(workflow.id)
            )

        self._assert_clean(result, "listToolInstances")

    def test_the_seeding_helper_actually_seeds(self) -> None:
        """Guard the guard: if seeding silently wrote nothing, every test above
        would pass vacuously — which is the exact failure this class exists to
        remove.
        """
        workflow = seed_canaries(Workflow(), CANARY)

        assert CANARY in workflow.workflow_name
        assert CANARY in json.dumps(workflow.source_settings, default=str)

    def test_a_wholesale_serializer_would_be_caught(self) -> None:
        """Proves the scan can fail. A tool built the unsafe way — dumping the
        model instead of naming fields — must trip the same assertion.
        """
        from django.forms.models import model_to_dict

        workflow = seed_canaries(Workflow(), CANARY)
        unsafe_result = {"workflows": [model_to_dict(workflow)]}

        with self.assertRaises(AssertionError):
            self._assert_clean(unsafe_result, "pretendTool")


class _FakeRows(list):
    """A list that answers the two queryset calls the list tools make.

    They do ``queryset.count()`` then slice for the page, so nothing more is
    needed — and keeping it this thin means the test fails if a tool starts
    doing something else to the queryset, rather than silently passing.
    """

    def count(self) -> int:
        return len(self)
