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

from django.test import SimpleTestCase

from mcp_server.tools.observability import redact_secrets


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
