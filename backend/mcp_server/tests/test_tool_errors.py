"""Tool-layer error messages, which are read by an agent rather than a human.

A tool error is the agent's next prompt: if it does not name the offending
argument in plain text, the agent's most likely next move is to retry the same
call — and for `extractDocument` a retry spends the organization's quota.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from mcp_server.tools.execution import _format_validation_error


class FormatValidationErrorTest(SimpleTestCase):
    def test_flattens_nested_detail_without_errordetail_repr(self) -> None:
        """DRF nests per-item errors under the field name and wraps each in an
        ``ErrorDetail``; both would otherwise reach the agent verbatim.
        """
        error = ValidationError({"presigned_urls": {0: ["Enter a valid URL."]}})

        message = _format_validation_error(error)

        assert message == "presigned_urls.0: Enter a valid URL."
        assert "ErrorDetail" not in message

    def test_reports_every_failing_field(self) -> None:
        """Surfacing only the first failure would send the agent round the loop
        once per bad argument.
        """
        error = ValidationError(
            {"timeout": ["Ensure this value is at most 300."], "tags": ["Invalid tag."]}
        )

        message = _format_validation_error(error)

        assert "timeout: Ensure this value is at most 300." in message
        assert "tags: Invalid tag." in message

    def test_plain_message_passes_through_unchanged(self) -> None:
        error = ValidationError("Something was wrong.")

        assert _format_validation_error(error) == "Something was wrong."


class DocumentUrlContractTest(SimpleTestCase):
    """What `extractDocument`'s docs promise vs what the serializer enforces.

    These are pinned together because they had already drifted apart. Every
    description said a URL without a signature is rejected; the validator only
    ever checked the *host*. The drift was not theoretical — two independent
    agent runs read that sentence, concluded a working call would be refused,
    and declined to make it, one of them noting the tool's own warning about
    speculative calls. A wrong doc string on an MCP tool is not cosmetic: the
    description *is* the interface, and it talked a valid call out of existing.
    """

    def _validate(self, url: str) -> str | None:
        """Return the rejection message, or None when the URL is accepted."""
        from api_v2.serializers import ExecutionRequestSerializer

        serializer = ExecutionRequestSerializer()
        try:
            serializer._validate_presigned_url(url)
        except ValidationError as error:
            return str(error.detail)
        return None

    def test_an_unsigned_public_s3_url_is_accepted(self) -> None:
        """The case the docs used to deny.

        A publicly-readable object needs no signature, and nothing in the
        validator asks for one. Confirmed end to end against a live deployment:
        an unsigned public S3 URL extracted successfully.
        """
        assert self._validate("https://s3.amazonaws.com/some-bucket/doc.pdf") is None

    def test_a_pre_signed_url_is_accepted(self) -> None:
        """The ordinary case: a private object reached with a signature."""
        signed = (
            "https://b.s3.us-east-1.amazonaws.com/doc.pdf"
            "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc"
        )

        assert self._validate(signed) is None

    def test_a_non_s3_host_is_rejected(self) -> None:
        """The restriction that *is* real, and the one the docs should state."""
        message = self._validate("https://evil.example.com/doc.pdf")

        assert message is not None
        assert "S3" in message

    def test_plain_http_is_rejected_even_on_an_s3_host(self) -> None:
        message = self._validate("http://s3.amazonaws.com/some-bucket/doc.pdf")

        assert message is not None
        assert "HTTPS" in message

    def test_no_description_claims_an_unsigned_url_is_rejected(self) -> None:
        """The docs must not re-acquire the claim the validator does not make.

        Asserted over the three places a client actually reads — the tool
        description, the argument schema, and the readMeFirst guide — because
        the wording was wrong in all three and fixing one would have left an
        agent reading either of the others.
        """
        from unittest.mock import MagicMock

        from mcp_server.registry import build_deployment_registry
        from mcp_server.tools.execution import extract_document_schema
        from mcp_server.tools.info import read_me_first

        context = MagicMock()
        context.api.display_name = "d"
        context.api.description = "d"
        context.api.is_active = True

        schema = extract_document_schema()
        extract_tool = build_deployment_registry().get("extractDocument")
        texts = {
            "document_urls schema": schema["properties"]["document_urls"]["description"],
            "extractDocument description": extract_tool.description,
            "readMeFirst notes": " ".join(read_me_first(context)["notes"]),
        }
        # Guarding the exact sentences that were wrong, not word proximity:
        # the corrected text legitimately contains both "publicly readable" and
        # "rejected" (of a non-S3 host), so a co-occurrence check fails on
        # correct wording.
        false_claims = (
            "only s3 pre-signed urls are accepted",
            "ordinary public link is rejected",
            "ordinary public links are rejected",
            "ordinary public http(s) link is rejected",
            "public links are rejected",
        )
        for label, text in texts.items():
            with self.subTest(label):
                lowered = " ".join(text.lower().split())
                # The restriction that is real must be stated.
                assert "s3" in lowered
                for claim in false_claims:
                    assert claim not in lowered, (
                        f"{label} still says {claim!r}; the validator checks the "
                        "host only, and accepts an unsigned public S3 URL"
                    )
