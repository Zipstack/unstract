"""Tests for provider response/request id extraction and logging."""

import logging
from functools import lru_cache
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest


@lru_cache(maxsize=1)
def _load_llm_module() -> object:
    import sys
    from types import ModuleType

    # Stub python-magic so importing LLM does not depend on libmagic
    # being available in the test environment.
    sys.modules.setdefault("magic", ModuleType("magic"))
    return import_module("unstract.sdk1.llm")


class _FakeModelResponse(dict):
    """Dict-like litellm ModelResponse stand-in with _hidden_params."""

    def __init__(
        self,
        *args: object,
        hidden_params: dict | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        if hidden_params is not None:
            self._hidden_params = hidden_params


def test_extract_provider_ids_openai_headers() -> None:
    llm_module = _load_llm_module()
    response = _FakeModelResponse(
        {"id": "chatcmpl-abc123"},
        hidden_params={
            "additional_headers": {
                "llm_provider-x-request-id": "req_openai_1",
                "llm_provider-content-type": "application/json",
            }
        },
    )

    assert llm_module.extract_provider_ids(response) == (
        "chatcmpl-abc123",
        "req_openai_1",
    )


def test_extract_provider_ids_anthropic_headers() -> None:
    llm_module = _load_llm_module()
    response = _FakeModelResponse(
        {"id": "msg_01XYZ"},
        hidden_params={
            "additional_headers": {"llm_provider-request-id": "req_anthropic_1"}
        },
    )

    assert llm_module.extract_provider_ids(response) == ("msg_01XYZ", "req_anthropic_1")


def test_extract_provider_ids_bedrock_headers() -> None:
    llm_module = _load_llm_module()
    response = _FakeModelResponse(
        {"id": "msg_bdrk_01"},
        hidden_params={
            "additional_headers": {"llm_provider-x-amzn-requestid": "req_aws_1"}
        },
    )

    assert llm_module.extract_provider_ids(response) == ("msg_bdrk_01", "req_aws_1")


def test_extract_provider_ids_prefers_x_request_id() -> None:
    llm_module = _load_llm_module()
    response = _FakeModelResponse(
        {"id": "chatcmpl-1"},
        hidden_params={
            "additional_headers": {
                "llm_provider-apim-request-id": "apim_1",
                "llm_provider-x-request-id": "req_1",
            }
        },
    )

    assert llm_module.extract_provider_ids(response) == ("chatcmpl-1", "req_1")


def test_extract_provider_ids_without_hidden_params() -> None:
    llm_module = _load_llm_module()

    # Plain dicts (and streaming chunks without headers) yield no request id.
    assert llm_module.extract_provider_ids({"id": "chatcmpl-2"}) == (
        "chatcmpl-2",
        None,
    )


def test_extract_provider_ids_handles_none_and_empty() -> None:
    llm_module = _load_llm_module()

    assert llm_module.extract_provider_ids(None) == (None, None)
    assert llm_module.extract_provider_ids({}) == (None, None)


def test_extract_provider_ids_falls_back_to_id_attribute() -> None:
    llm_module = _load_llm_module()

    class _AttrOnlyResponse:
        id = "chatcmpl-attr"

        def get(self, key: str) -> None:
            return None

    assert llm_module.extract_provider_ids(_AttrOnlyResponse()) == (
        "chatcmpl-attr",
        None,
    )


def _build_llm_for_record_usage(llm_cls: type) -> object:
    llm = llm_cls.__new__(llm_cls)
    llm._platform_api_key = "platform-key"
    llm.platform_kwargs = {"run_id": "run-1"}
    llm._usage_kwargs = {}
    llm._pending_usage = []
    llm.adapter = MagicMock()
    llm.adapter.get_provider.return_value = "openai"
    return llm


def test_record_usage_logs_provider_ids(caplog: pytest.LogCaptureFixture) -> None:
    llm_module = _load_llm_module()
    llm = _build_llm_for_record_usage(llm_module.LLM)
    response = _FakeModelResponse(
        {"id": "chatcmpl-log1"},
        hidden_params={"additional_headers": {"llm_provider-x-request-id": "req_log_1"}},
    )

    with (
        patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)),
        caplog.at_level(logging.INFO, logger=llm_module.logger.name),
    ):
        llm._record_usage(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            llm_api="complete",
            response=response,
        )

    usage_logs = [r.message for r in caplog.records if "Usage:" in r.message]
    assert len(usage_logs) == 1
    assert "response_id=chatcmpl-log1" in usage_logs[0]
    assert "request_id=req_log_1" in usage_logs[0]


def test_record_usage_logs_without_response(caplog: pytest.LogCaptureFixture) -> None:
    llm_module = _load_llm_module()
    llm = _build_llm_for_record_usage(llm_module.LLM)

    with (
        patch.object(llm_module.litellm, "cost_per_token", return_value=(0.0, 0.0)),
        caplog.at_level(logging.INFO, logger=llm_module.logger.name),
    ):
        llm._record_usage(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            llm_api="complete",
        )

    usage_logs = [r.message for r in caplog.records if "Usage:" in r.message]
    assert len(usage_logs) == 1
    # Absent ids are omitted to keep the line compact.
    assert "response_id" not in usage_logs[0]
    assert "request_id" not in usage_logs[0]
