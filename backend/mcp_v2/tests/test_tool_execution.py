"""The success path of the extraction tools.

The transport and auth tests never reach these helpers on a successful call, so
without this file the argument mapping from tool kwargs into
``execute_workflow`` is executed by nothing — a renamed or mis-mapped kwarg
would pass every other test and fail on the first real extraction. The
``assert_called_once_with`` below is the point of these tests.

Mocked at the ``DeploymentHelper`` boundary so no database or Celery is needed.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from workflow_manager.workflow_v2.dto import ExecutionResponse

from mcp_v2.context import MCPContext
from mcp_v2.exceptions import MCPToolError
from mcp_v2.tools.execution import extract_document, get_execution_status

# The execution serializer accepts only HTTPS S3 pre-signed URLs; using a
# realistic one here keeps these tests honest about what the tool accepts.
DOC_URL = "https://my-bucket.s3.us-east-1.amazonaws.com/invoice.pdf?X-Amz-Signature=abc"
EXECUTION_ID = "33333333-3333-3333-3333-333333333333"


class FakeOrganization:
    organization_id = "org-mcp"


class FakeAPI:
    display_name = "Invoice Extractor"
    api_name = "live-api"
    is_active = True
    organization = FakeOrganization()


def make_context(active: bool = True) -> MCPContext:
    api = FakeAPI()
    api.is_active = active
    return MCPContext(api=api, api_key="test-key", org_name="org-mcp")


class ExtractDocumentTest(SimpleTestCase):
    def setUp(self) -> None:
        self.context = make_context()

    def _run(self, execute_return=None, **kwargs):
        """Drive extract_document with the whole execution stack stubbed."""
        with (
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.load_presigned_files"
            ) as load_files,
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.check_and_acquire",
                return_value=(True, {}),
            ),
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.release_slot"
            ) as release,
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.execute_workflow",
                return_value=execute_return
                if execute_return is not None
                else {"execution_status": "COMPLETED", "message": "ok"},
            ) as execute,
        ):
            result = extract_document(self.context, **kwargs)
        return result, execute, load_files, release

    def test_arguments_map_onto_execute_workflow(self) -> None:
        """Guards the tool-kwarg -> execute_workflow mapping. A rename on
        either side breaks here rather than in production.
        """
        result, execute, load_files, _ = self._run(
            document_urls=[DOC_URL],
            timeout=45,
            include_metadata=True,
            include_metrics=True,
            include_extracted_text=True,
            tags=["alpha"],
        )

        load_files.assert_called_once()
        assert load_files.call_args.args[0] == [DOC_URL]

        execute.assert_called_once()
        kwargs = execute.call_args.kwargs
        assert kwargs["organization_name"] == "org-mcp"
        assert kwargs["api"] is self.context.api
        assert kwargs["timeout"] == 45
        assert kwargs["include_metadata"] is True
        assert kwargs["include_metrics"] is True
        assert kwargs["include_extracted_text"] is True
        # Agents send a JSON array; the execution layer expects parsed names.
        assert kwargs["tag_names"] == ["alpha"]
        assert kwargs["execution_id"] == result["execution_id"]

    def test_result_always_carries_execution_id(self) -> None:
        """On the pending path the id is the agent's only handle for polling,
        and execute_workflow does not guarantee it in the body.
        """
        result, execute, _, _ = self._run(
            execute_return={"execution_status": "PENDING"}, document_urls=[DOC_URL]
        )

        assert result["execution_status"] == "PENDING"
        assert result["execution_id"] == execute.call_args.kwargs["execution_id"]

    def test_existing_execution_id_in_response_is_preserved(self) -> None:
        """Never overwrite an id the execution layer reported itself."""
        result, _, _, _ = self._run(
            execute_return={"execution_status": "COMPLETED", "execution_id": "from-core"},
            document_urls=[DOC_URL],
        )

        assert result["execution_id"] == "from-core"

    def test_defaults_are_conservative(self) -> None:
        """Defaults must not silently opt an agent into large or costly output."""
        _, execute, _, _ = self._run(document_urls=[DOC_URL])

        kwargs = execute.call_args.kwargs
        assert kwargs["include_metadata"] is False
        assert kwargs["include_metrics"] is False
        assert kwargs["include_extracted_text"] is False
        assert kwargs["tag_names"] == []

    def test_inactive_deployment_rejected_before_quota_is_spent(self) -> None:
        with patch(
            "mcp_v2.tools.execution.DeploymentHelper.execute_workflow"
        ) as execute:
            with self.assertRaises(MCPToolError):
                extract_document(make_context(active=False), document_urls=[DOC_URL])

        execute.assert_not_called()

    def test_non_s3_url_rejected_with_an_explanation(self) -> None:
        """Only S3 pre-signed URLs are accepted. The tool description says so,
        and this pins the behaviour the description promises — an agent handed
        an ordinary link must be told why, not just that it failed.
        """
        with patch(
            "mcp_v2.tools.execution.DeploymentHelper.execute_workflow"
        ) as execute:
            with self.assertRaises(MCPToolError) as caught:
                extract_document(
                    self.context, document_urls=["https://example.com/invoice.pdf"]
                )

        execute.assert_not_called()
        assert "S3" in str(caught.exception)

    def test_invalid_url_rejected_before_quota_is_spent(self) -> None:
        with (
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.check_and_acquire"
            ) as acquire,
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.execute_workflow"
            ) as execute,
        ):
            with self.assertRaises(MCPToolError):
                extract_document(self.context, document_urls=["not-a-url"])

        acquire.assert_not_called()
        execute.assert_not_called()

    def test_rate_limited_call_downloads_nothing(self) -> None:
        """The slot is taken before the documents are fetched, so a rejected
        call must not pull every document over the network first.
        """
        with (
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.load_presigned_files"
            ) as load_files,
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.check_and_acquire",
                return_value=(
                    False,
                    {"current_usage": 5, "limit": 5, "limit_type": "organization"},
                ),
            ),
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.execute_workflow"
            ) as execute,
        ):
            with self.assertRaises(MCPToolError) as caught:
                extract_document(self.context, document_urls=[DOC_URL])

        load_files.assert_not_called()
        execute.assert_not_called()
        assert "5/5" in str(caught.exception)

    def test_failed_download_releases_the_rate_limit_slot(self) -> None:
        """The fetch happens after the slot is taken, so a fetch failure has to
        give the slot back or the org silently loses throughput.
        """
        with (
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.load_presigned_files",
                side_effect=RuntimeError("403 Forbidden"),
            ),
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.check_and_acquire",
                return_value=(True, {}),
            ),
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.release_slot"
            ) as release,
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.execute_workflow"
            ) as execute,
        ):
            with self.assertRaises(MCPToolError):
                extract_document(self.context, document_urls=[DOC_URL])

        release.assert_called_once()
        execute.assert_not_called()

    def test_failed_execution_releases_the_rate_limit_slot(self) -> None:
        """A leaked slot degrades the org's throughput permanently, so the
        release must survive the failure path.
        """
        with (
            patch("mcp_v2.tools.execution.DeploymentHelper.load_presigned_files"),
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.check_and_acquire",
                return_value=(True, {}),
            ),
            patch(
                "mcp_v2.tools.execution.APIDeploymentRateLimiter.release_slot"
            ) as release,
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.execute_workflow",
                side_effect=RuntimeError("boom"),
            ),
        ):
            with self.assertRaises(MCPToolError):
                extract_document(self.context, document_urls=[DOC_URL])

        release.assert_called_once()


class GetExecutionStatusTest(SimpleTestCase):
    def setUp(self) -> None:
        self.context = make_context()

    def _run(self, response: ExecutionResponse, **kwargs):
        with (
            patch(
                "mcp_v2.tools.execution.ExecutionQuerySerializer.is_valid",
                return_value=True,
            ),
            patch(
                "mcp_v2.tools.execution.ExecutionQuerySerializer.validated_data",
                {
                    "execution_id": EXECUTION_ID,
                    "include_metadata": kwargs.get("include_metadata", False),
                    "include_metrics": kwargs.get("include_metrics", False),
                    "include_extracted_text": kwargs.get(
                        "include_extracted_text", False
                    ),
                },
            ),
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.get_execution_status",
                return_value=response,
            ),
            patch(
                "mcp_v2.tools.execution.DeploymentHelper.process_completed_execution"
            ) as process,
        ):
            result = get_execution_status(
                self.context, execution_id=EXECUTION_ID, **kwargs
            )
        return result, process

    def test_completed_execution_is_enriched_and_returned(self) -> None:
        response = ExecutionResponse(
            workflow_id="wf",
            execution_id=EXECUTION_ID,
            execution_status="COMPLETED",
            result=[{"file": "invoice.pdf", "result": {"output": {"total": 42}}}],
        )

        result, process = self._run(response, include_metadata=True)

        # Enrichment is what turns the raw execution into the API-shaped
        # result; skipping it would silently return a thinner payload.
        process.assert_called_once()
        assert process.call_args.kwargs["include_metadata"] is True
        assert result["execution_status"] == "COMPLETED"
        assert result["result"][0]["result"]["output"]["total"] == 42
        assert result["execution_id"] == EXECUTION_ID

    def test_pending_execution_is_not_enriched(self) -> None:
        response = ExecutionResponse(
            workflow_id="wf",
            execution_id=EXECUTION_ID,
            execution_status="EXECUTING",
            result=None,
        )

        result, process = self._run(response)

        process.assert_not_called()
        assert result["execution_status"] == "EXECUTING"

    def test_acknowledged_result_explains_itself(self) -> None:
        """The REST surface answers 406 here; an agent cannot act on a status
        code, so the tool must say the result is gone and not retryable.
        """
        response = ExecutionResponse(
            workflow_id="wf",
            execution_id=EXECUTION_ID,
            execution_status="COMPLETED",
            result=None,
        )
        response.result_acknowledged = True

        result, process = self._run(response)

        process.assert_not_called()
        assert "already acknowledged" in result["message"]

    def test_unknown_execution_id_is_an_agent_error(self) -> None:
        """A bad id comes back as an actionable tool error, not a server
        fault — the agent may simply have mistyped it.
        """
        with patch(
            "mcp_v2.tools.execution.ExecutionQuerySerializer.is_valid",
            side_effect=ValidationError({"execution_id": ["Invalid execution_id."]}),
        ):
            with self.assertRaises(MCPToolError) as caught:
                get_execution_status(self.context, execution_id="nope")

        assert "execution_id" in str(caught.exception)
