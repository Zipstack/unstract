"""Provider failure details on the executor's failure result.

A provider error (litellm / OpenAI SDK exception) is wrapped by sdk1 in an
``LLMError`` and by the executor in a ``LegacyExecutorError``. The failure
result's metadata carries the provider name, request id and retry hint found
on that chain, so the IDE callback can show them.
"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import patch

import httpx
import litellm
import pytest
from executor.executors.exceptions import LegacyExecutorError, RateLimitError
from executor.executors.provider_error_details import provider_error_details

from unstract.sdk1.exceptions import LLMError


def _provider_error(headers=None, provider="azure", status=429, response_headers=None):
    response = httpx.Response(
        status,
        headers=headers or {},
        request=httpx.Request("POST", "https://provider.invalid"),
    )
    err = litellm.RateLimitError(
        "rate limit exceeded", llm_provider=provider, model="gpt-4o", response=response
    )
    if response_headers is not None:
        err.litellm_response_headers = response_headers
    return err


def _wrapped(provider_err, outer=LegacyExecutorError):
    """Mirror the chain sdk1 and the executor build: outer <- LLMError <- provider."""
    try:
        try:
            try:
                raise provider_err
            except Exception as e:
                raise LLMError(message=str(e), actual_err=e) from e
        except LLMError as e:
            raise outer(message=f"Rate limit error. {e}") from e
    except LegacyExecutorError as e:
        return e


class TestProviderErrorDetails:
    def test_reads_provider_request_id_and_retry_hint(self):
        err = _provider_error({"retry-after": "60", "x-request-id": "req-1"})

        assert provider_error_details(_wrapped(err)) == {
            "provider": "azure",
            "request_id": "req-1",
            "retry_after_seconds": 60,
        }

    def test_found_through_the_executor_rate_limit_wrapper(self):
        err = _provider_error({"retry-after": "5"})

        details = provider_error_details(_wrapped(err, outer=RateLimitError))

        assert details["retry_after_seconds"] == 5

    def test_reads_litellm_response_headers(self):
        err = _provider_error(
            response_headers={"Retry-After-Ms": "1500", "apim-request-id": "az-7"}
        )

        details = provider_error_details(_wrapped(err))

        assert details["request_id"] == "az-7"
        assert details["retry_after_seconds"] == 2

    def test_anthropic_request_id_header(self):
        err = _provider_error({"request-id": "req_011"}, provider="anthropic")

        assert provider_error_details(_wrapped(err))["request_id"] == "req_011"

    def test_retry_after_as_http_date(self):
        when = datetime.now(UTC) + timedelta(seconds=90)
        err = _provider_error({"retry-after": format_datetime(when, usegmt=True)})

        seconds = provider_error_details(_wrapped(err))["retry_after_seconds"]

        assert 85 <= seconds <= 90

    def test_retry_after_date_without_zone(self):
        when = datetime.now(UTC) + timedelta(seconds=90)
        err = _provider_error({"retry-after": format_datetime(when.replace(tzinfo=None))})

        seconds = provider_error_details(_wrapped(err))["retry_after_seconds"]

        assert 85 <= seconds <= 90

    def test_retry_after_date_in_the_past_is_zero(self):
        when = datetime.now(UTC) - timedelta(minutes=5)
        err = _provider_error({"retry-after": format_datetime(when, usegmt=True)})

        assert provider_error_details(_wrapped(err))["retry_after_seconds"] == 0

    @pytest.mark.parametrize("value", ["soon", "-5", "nan", "inf", ""])
    def test_unusable_retry_after_is_null(self, value):
        err = _provider_error({"retry-after": value, "x-request-id": "req-1"})

        assert provider_error_details(_wrapped(err))["retry_after_seconds"] is None

    def test_found_through_actual_err_without_cause(self):
        err = _provider_error({"x-request-id": "req-2"})
        wrapper = LLMError(message="wrapped", actual_err=err)

        assert provider_error_details(wrapper)["request_id"] == "req-2"

    def test_long_values_truncated(self):
        err = _provider_error({"x-request-id": "r" * 500}, provider="p" * 500)

        details = provider_error_details(_wrapped(err))

        assert len(details["request_id"]) == 128
        assert len(details["provider"]) == 128

    def test_no_provider_error_in_chain(self):
        try:
            try:
                raise ValueError("bad prompt")
            except ValueError as e:
                raise LegacyExecutorError(message="bad prompt") from e
        except LegacyExecutorError as exc:
            assert provider_error_details(exc) is None

    def test_provider_error_without_any_detail(self):
        err = _provider_error(provider="")

        assert provider_error_details(_wrapped(err)) is None

    def test_self_referencing_chain_terminates(self):
        exc = LegacyExecutorError(message="loop")
        exc.__context__ = exc

        assert provider_error_details(exc) is None

    def test_never_raises(self):
        err = _provider_error({"x-request-id": "req-1"})
        with patch(
            "executor.executors.provider_error_details._headers",
            side_effect=RuntimeError("broken"),
        ):
            assert provider_error_details(_wrapped(err)) is None


class TestLegacyExecutorFailureMetadata:
    def _execute(self, handler_exc):
        from executor.executors.legacy_executor import LegacyExecutor

        from unstract.sdk1.execution.context import ExecutionContext

        context = ExecutionContext(
            executor_name="legacy",
            operation="answer_prompt",
            run_id="run-1",
            execution_source="ide",
            organization_id="org-1",
            request_id="req-1",
        )
        executor = LegacyExecutor()

        def _raise(_ctx):
            raise handler_exc

        with patch.object(executor, "_handle_answer_prompt", side_effect=_raise):
            return executor.execute(context)

    def test_failure_metadata_carries_error_details(self):
        err = _provider_error({"retry-after": "60", "x-request-id": "req-1"})

        result = self._execute(_wrapped(err))

        assert result.success is False
        assert result.error.startswith("Rate limit error.")
        assert result.metadata["error_details"] == {
            "provider": "azure",
            "request_id": "req-1",
            "retry_after_seconds": 60,
        }

    def test_no_error_details_key_without_provider_error(self):
        result = self._execute(LegacyExecutorError(message="bad prompt"))

        assert result.success is False
        assert "error_details" not in result.metadata
