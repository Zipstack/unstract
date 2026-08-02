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

from mcp_server.sanitize import redact_secrets, redact_structure


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


class SecretAnchorTest(SimpleTestCase):
    """The literal pre-filter must never change what redaction produces.

    ``redact_secrets`` skips its regex passes when none of ``_SECRET_ANCHORS``
    appears in the text. That is a pure speed optimisation — it walks every
    string in an execution result, including raw OCR text — so it is only safe
    while every pattern genuinely requires one of those literals. A new pattern
    added without its anchor would silently stop matching.
    """

    def _unfiltered(self, text: str) -> str:
        from mcp_server.sanitize import _SECRET_PATTERNS

        out = text
        for pattern, replacement in _SECRET_PATTERNS:
            out = pattern.sub(replacement, out)
        return out

    def test_every_pattern_is_reachable_through_the_anchors(self) -> None:
        """One representative match per pattern, asserted equal both ways."""
        cases = [
            "Authorization: Bearer abcdef123456",
            "connect failed: password=hunter2",
            "auth error api_key=sk-abc123",
            "api-key = sk-abc123",
            "secret_access_key=AKIAIOSFODNN7EXAMPLE",
            "bad token=eyJhbGciOi",
            "could not connect to postgresql://admin:s3cr3tpw@db:5432/x",
            "PASSWORD: hunter2",
        ]
        for text in cases:
            with self.subTest(text):
                assert redact_secrets(text) == self._unfiltered(text)
                assert "[REDACTED]" in redact_secrets(text)

    def test_anchorless_text_is_returned_untouched(self) -> None:
        text = "File not found: invoice-2024-03.pdf (no such object in bucket)"

        assert redact_secrets(text) == self._unfiltered(text) == text

    def test_unicode_case_folding_does_not_slip_past_the_filter(self) -> None:
        """The pre-filter must not disagree with the regex about case.

        ``(?i)`` and ``str.lower()`` are different functions: the regex engine
        folds U+017F (ſ) to "s" and U+212A (K) to "k"; ``.lower()`` leaves both
        alone. So these strings match a pattern while containing no anchor once
        lowercased. An ASCII-only gate on the fast path is what keeps them
        going through the regexes — without it, each is a live credential leak.
        """
        cases = [
            "pa\u017f\u017fword=hunter2",
            "\u017fecret: abc123",
            "\u017fecret_acce\u017f\u017f_key=AKIA1234",
            "PA\u017f\u017fWORD=hunter2",
            "to\u212aen=zzz",
        ]
        for text in cases:
            with self.subTest(text):
                assert redact_secrets(text) == self._unfiltered(text)
                assert "[REDACTED]" in redact_secrets(text), (
                    f"{text!r} matches a secret pattern but was not redacted"
                )

    def test_the_filter_never_changes_output_over_a_generated_corpus(self) -> None:
        """The invariant as a property, not a hand-kept list.

        A hand-listed corpus only catches what someone thought to add — which
        is exactly the step a change that adds a pattern forgets. This builds
        inputs from the pattern vocabulary itself, including the case-folding
        characters, so a new pattern without its anchor fails here.
        """
        import itertools

        keys = [
            "password", "passwd", "pwd", "secret", "access_key",
            "secret_access_key", "apikey", "api_key", "api-key", "token",
            "authorization", "credential", "bearer",
        ]
        # Case variants, including the two characters the regex folds and
        # str.lower() does not.
        def variants(word: str):
            yield word
            yield word.upper()
            yield word.replace("s", "\u017f")
            yield word.replace("k", "\u212a")

        seps = ["=", ": ", " = "]
        corpus = []
        for key, sep in itertools.product(
            (v for k in keys for v in variants(k)), seps
        ):
            corpus.append(f"connect failed: {key}{sep}s3cr3t (code 28P01)")
        corpus += [
            "postgresql://admin:pw@host:5432/db",
            "POSTGRESQL://ADMIN:PW@HOST/DB",
            "ordinary text with no secrets",
            "invoice-2024.pdf not found",
            "",
        ]

        for text in corpus:
            with self.subTest(text[:48]):
                assert redact_secrets(text) == self._unfiltered(text)


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

    def test_sequences_become_plain_lists(self) -> None:
        """Sequence subclasses are normalised, not reconstructed.

        Rebuilding via ``type(value)(...)`` raises for anything whose __init__
        is not "an iterable" — which on this path means a crash on the return
        of a billable tool, after the money was already spent.
        """
        out = redact_structure(("password=hunter2", "plain"))

        assert isinstance(out, list)
        assert "hunter2" not in out[0]
        assert out[1] == "plain"

    def test_a_namedtuple_does_not_raise(self) -> None:
        from typing import NamedTuple

        class Row(NamedTuple):
            secret: str
            name: str

        out = redact_structure(Row(secret="password=hunter2", name="a.pdf"))

        assert "hunter2" not in out[0]
        assert out[1] == "a.pdf"

    def test_a_drf_return_list_does_not_raise(self) -> None:
        """``ReturnList.__init__`` requires a ``serializer`` kwarg.

        Reachable because the write paths return whatever a delegated
        ``many=True`` serializer produced.
        """
        from rest_framework.utils.serializer_helpers import ReturnList

        payload = ReturnList([{"error": "password=hunter2"}], serializer=object())

        out = redact_structure({"results": payload})

        assert "hunter2" not in json.dumps(out, default=str)

    def test_nested_sequence_subclass_inside_a_dict(self) -> None:
        """The dict branch recurses into the sequence branch, so a nested
        subclass hits the same path a top-level one would.
        """
        from rest_framework.utils.serializer_helpers import ReturnList

        payload = {
            "outer": {"inner": ReturnList(["api_key=sk-abc"], serializer=object())}
        }

        out = redact_structure(payload)

        assert "sk-abc" not in json.dumps(out, default=str)


class SecretKeyNameTest(SimpleTestCase):
    """A credential-named key with a bare value is redacted.

    The text patterns anchor on a delimiter — `password=x`, `Bearer x`,
    `scheme://u:p@h` — so `{"api_key": "sk-abc"}` matched none of them and
    passed through untouched. That is the ordinary shape of serializer output,
    i.e. exactly what the delegating tools return, so it was the most likely
    leak rather than an edge case. Found by the write-tool leak sweep.
    """

    def test_a_credential_named_key_is_redacted(self) -> None:
        for key in (
            "password",
            "api_key",
            "api-key",
            "apiKey",
            "token",
            "access_token",
            "client_secret",
            "private_key",
            "secret_access_key",
            "CREDENTIALS",
        ):
            with self.subTest(key):
                out = redact_structure({key: "sk-abc123"})
                assert out[key] == "[REDACTED]"

    def test_it_reaches_nested_and_listed_values(self) -> None:
        out = redact_structure(
            {"profile": {"api_key": "sk-abc"}, "rows": [{"token": "t-1"}]}
        )

        assert out["profile"]["api_key"] == "[REDACTED]"
        assert out["rows"][0]["token"] == "[REDACTED]"

    def test_camel_case_credential_keys_are_redacted(self) -> None:
        """AWS-style and JS-style names arrive camelCased in upstream JSON.

        `.lower()` alone compresses `secretAccessKey` to `secretaccesskey`,
        which matches nothing — so the camel boundary has to be split *before*
        lowercasing. These were live leaks until that was fixed.
        """
        for key in (
            "secretAccessKey",
            "accessKeyId",
            "clientSecret",
            "authToken",
            "refreshToken",
            "privateKey",
            "apiKey",
        ):
            with self.subTest(key):
                assert redact_structure({key: "sk-abc"})[key] == "[REDACTED]"

    def test_mixed_separators_normalise_the_same_way(self) -> None:
        for key in ("Api-Key", "API_KEY", "Access Key", "refresh-token"):
            with self.subTest(key):
                assert redact_structure({key: "sk-abc"})[key] == "[REDACTED]"

    def test_ordinary_fields_are_not_redacted(self) -> None:
        """The false-positive guard. Over-redacting makes output unusable to an
        agent without making it safer, so the match is exact rather than a
        substring test.
        """
        payload = {
            "token_count": 1280,
            "has_credentials": True,
            "secret_santa": "Bob",
            "password_hint": "your usual one",
            "tokens_used": 42,
            "authorization_status": "approved",
        }

        assert redact_structure(payload) == payload

    def test_non_string_values_are_left_alone(self) -> None:
        """A credential-named key holding a non-string is not a leaked secret,
        and blanking it would destroy structure an agent reads.
        """
        payload = {"token": None, "api_key": 0, "secret": {"nested": "value"}}
        out = redact_structure(payload)

        assert out["token"] is None
        assert out["api_key"] == 0
        assert out["secret"] == {"nested": "value"}

    def test_key_and_text_redaction_compose(self) -> None:
        out = redact_structure(
            {"api_key": "sk-abc", "log": "connect failed: password=hunter2"}
        )

        assert out["api_key"] == "[REDACTED]"
        assert "hunter2" not in out["log"]


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

    def test_extract_document_result_is_redacted(self) -> None:
        from unittest.mock import MagicMock, patch

        from mcp_server.tools.execution import extract_document

        context = MagicMock()
        context.api.is_active = True

        with (
            patch(
                "mcp_server.tools.execution.ExecutionRequestSerializer.is_valid",
                return_value=True,
            ),
            patch(
                "mcp_server.tools.execution.ExecutionRequestSerializer.validated_data",
                {
                    "presigned_urls": [
                        "https://x.s3.amazonaws.com/a.pdf?X-Amz-Signature=z"
                    ]
                },
            ),
            patch(
                "mcp_server.tools.execution.APIDeploymentRateLimiter.check_and_acquire",
                return_value=(True, {}),
            ),
            patch("mcp_server.tools.execution.DeploymentHelper.load_presigned_files"),
            patch(
                "mcp_server.tools.execution.DeploymentHelper.execute_workflow",
                return_value={"error": self.CANARY},
            ),
        ):
            out = extract_document(
                context,
                document_urls=["https://x.s3.amazonaws.com/a.pdf?X-Amz-Signature=z"],
            )

        assert "hunter2" not in json.dumps(out, default=str)

    def test_execute_pipeline_result_is_redacted(self) -> None:
        from unittest.mock import MagicMock, patch

        from mcp_server.tools.platform import execute_pipeline

        context = MagicMock()
        context.org_name = "org-mcp"
        response = MagicMock()
        response.status_code = 200
        response.data = {"detail": self.CANARY}

        pipeline = MagicMock()
        pipeline.id = "p1"
        pipeline.pipeline_name = "P"

        with (
            patch("mcp_server.tools.platform._resolve_pipeline", return_value=pipeline),
            patch(
                "pipeline_v2.manager.PipelineManager.execute_pipeline",
                return_value=response,
            ),
        ):
            out = execute_pipeline(context, pipeline_id="p1")

        assert "hunter2" not in json.dumps(out, default=str)
