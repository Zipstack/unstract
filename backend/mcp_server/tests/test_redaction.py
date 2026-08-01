"""Redaction of credential-shaped text in execution errors.

Structured fields are safe because they are named explicitly. Free-form error
text is not: a connector that fails to connect reports the connection string it
tried, and a provider client echoes the key it authenticated with. That text
goes straight to the agent, so it is scrubbed first.

This was found by ``test_no_credential_leak`` rather than by review — the
canary seeded in an execution's ``error_message`` came back through
``listExecutions``.
"""

from __future__ import annotations

import json

from django.test import SimpleTestCase

from mcp_server.tools.observability import redact_secrets, redact_structure


class RedactSecretsTest(SimpleTestCase):
    def test_key_value_secrets_are_masked(self) -> None:
        cases = [
            "connect failed: password=hunter2",
            "connect failed: PASSWORD: hunter2",
            "auth error api_key=sk-abc123",
            "auth error api-key = sk-abc123",
            "bad token=eyJhbGciOi",
            "secret_access_key=AKIAIOSFODNN7EXAMPLE",
        ]
        for text in cases:
            with self.subTest(text):
                out = redact_secrets(text)
                assert "[REDACTED]" in out
                for leaked in ("hunter2", "sk-abc123", "eyJhbGciOi", "AKIA"):
                    assert leaked not in out

    def test_connection_string_password_is_masked(self) -> None:
        out = redact_secrets(
            "could not connect to postgresql://admin:s3cr3tpw@db.internal:5432/x"
        )

        assert "s3cr3tpw" not in out
        assert "[REDACTED]" in out
        # The rest of the URL survives, or the message stops being diagnosable.
        assert "db.internal:5432" in out
        assert "admin" in out

    def test_bearer_token_is_masked(self) -> None:
        out = redact_secrets("401 from provider, sent Authorization: Bearer abcdef123456")

        assert "abcdef123456" not in out
        assert "[REDACTED]" in out

    def test_surrounding_message_is_preserved(self) -> None:
        """Redaction that eats the whole message would trade one problem for
        another — the agent still has to be able to diagnose the failure.
        """
        out = redact_secrets(
            "Failed after 3 attempts on table `invoices`: password=hunter2 (code 28P01)"
        )

        assert "Failed after 3 attempts" in out
        assert "invoices" in out
        assert "28P01" in out
        assert "hunter2" not in out

    def test_ordinary_error_text_is_untouched(self) -> None:
        text = "File not found: invoice-2024-03.pdf (no such object in bucket)"

        assert redact_secrets(text) == text

    def test_empty_and_none_are_safe(self) -> None:
        assert redact_secrets(None) is None
        assert redact_secrets("") == ""

    def test_multiple_secrets_in_one_message_are_all_masked(self) -> None:
        out = redact_secrets("password=one and api_key=two and token=three")

        for leaked in ("one", "two", "three"):
            assert f"={leaked}" not in out
        assert out.count("[REDACTED]") == 3


class RedactStructureTest(SimpleTestCase):
    """Redaction of upstream payloads the billable and write tools return.

    The read tools serialize named fields, so what they return is known. The
    billable and write tools hand back whatever the delegated view or execution
    helper produced — ``response.data`` including non-2xx error bodies, and raw
    execution results — which is exactly where a failed connector's error text
    arrives verbatim. Previously only free-form error *messages* were scrubbed,
    so ``redact_secrets``'s docstring claimed a coverage it did not have.
    """

    def test_nested_dict_values_are_masked(self) -> None:
        out = redact_structure(
            {
                "error": {
                    "detail": "connect failed: password=hunter2",
                    "code": "28P01",
                }
            }
        )

        assert "hunter2" not in out["error"]["detail"]
        assert out["error"]["code"] == "28P01"

    def test_secrets_inside_lists_are_masked(self) -> None:
        out = redact_structure(
            [
                {"file": "a.pdf", "error": "api_key=sk-abc123"},
                {"file": "b.pdf", "error": None},
            ]
        )

        assert "sk-abc123" not in out[0]["error"]
        assert out[0]["file"] == "a.pdf"
        assert out[1]["error"] is None

    def test_non_string_leaves_are_preserved(self) -> None:
        """Redaction must not coerce types — an agent reads these as data."""
        payload = {"count": 3, "ok": True, "ratio": 1.5, "missing": None}

        assert redact_structure(payload) == payload

    def test_the_input_is_not_mutated(self) -> None:
        """Containers are rebuilt, so reporting a cached dict or a queryset row
        must not scrub the caller's own copy as a side effect.
        """
        original = {"error": "password=hunter2"}

        redact_structure(original)

        assert original["error"] == "password=hunter2"

    def test_tuples_keep_their_type(self) -> None:
        out = redact_structure(("password=hunter2", "plain"))

        assert isinstance(out, tuple)
        assert "hunter2" not in out[0]
        assert out[1] == "plain"


class WriteToolRedactionCallSitesTest(SimpleTestCase):
    """The billable and write paths actually apply the net.

    ``test_no_credential_leak`` sweeps only the read tools — invoking the
    others would start real executions and spend real budget — so without
    these, dropping a ``redact_structure`` call from a write path would be
    caught by nothing. Each test drives the real function with the upstream
    boundary stubbed to return a canary.
    """

    CANARY = "connect failed: password=hunter2"

    def test_prompt_studio_result_is_redacted(self) -> None:
        from unittest.mock import MagicMock

        from mcp_server.tools.prompt_studio import _result

        response = MagicMock()
        response.status_code = 400
        # Non-2xx bodies are returned as data rather than raised, which is
        # exactly where a delegated view's error text arrives verbatim.
        response.data = {"detail": self.CANARY}
        project = MagicMock()
        project.tool_id = "p1"
        project.tool_name = "P"

        out = _result(response, project)

        assert "hunter2" not in json.dumps(out, default=str)

    def test_execution_status_result_is_redacted(self) -> None:
        from unittest.mock import MagicMock, patch

        from workflow_manager.workflow_v2.dto import ExecutionResponse

        from mcp_server.tools.execution import get_execution_status

        response = ExecutionResponse(
            workflow_id="wf",
            execution_id="e1",
            execution_status="COMPLETED",
            result=[{"file": "a.pdf", "error": self.CANARY}],
        )
        context = MagicMock()
        context.api.workflow_id = "wf"

        with (
            patch("mcp_server.tools.execution.WorkflowExecution.objects.filter") as f,
            patch(
                "mcp_server.tools.execution.ExecutionQuerySerializer.is_valid",
                return_value=True,
            ),
            patch(
                "mcp_server.tools.execution.ExecutionQuerySerializer.validated_data",
                {
                    "execution_id": "11111111-1111-1111-1111-111111111111",
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
                "mcp_server.tools.execution.DeploymentHelper.process_completed_execution"
            ),
        ):
            f.return_value.only.return_value.first.return_value = object()
            out = get_execution_status(
                context, execution_id="11111111-1111-1111-1111-111111111111"
            )

        assert "hunter2" not in json.dumps(out, default=str)
