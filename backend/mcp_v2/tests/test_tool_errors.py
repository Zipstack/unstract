"""Tool-layer error messages, which are read by an agent rather than a human.

A tool error is the agent's next prompt: if it does not name the offending
argument in plain text, the agent's most likely next move is to retry the same
call — and for `extractDocument` a retry spends the organization's quota.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from mcp_v2.tools.execution import _format_validation_error


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
