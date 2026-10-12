"""Model-aware image limits at extraction time (UN-4427).

The extract handler resolves the limits of the LLM(s) that will consume an
image-mode document BEFORE LLMWhisperer converts (and bills) it, passes the
policy into the x2text adapter, fails closed when limits cannot be
resolved, and keeps the machine-readable code on extraction errors.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from executor.executors import image_limits as exec_limits  # noqa: E402
from executor.executors.constants import IndexingConstants as IKeys  # noqa: E402
from executor.executors.exceptions import ExtractionError  # noqa: E402
from executor.executors.legacy_executor import LegacyExecutor  # noqa: E402

from unstract.sdk1.adapters.exceptions import (  # noqa: E402
    ExtractorError,
    ImageLimitExceededError,
)
from unstract.sdk1.adapters.x2text.constants import X2TextConstants  # noqa: E402
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import (  # noqa: E402
    LLMWhispererV2,
)
from unstract.sdk1.execution.context import ExecutionContext  # noqa: E402
from unstract.sdk1.utils.image_limits import ImageModePolicy, codes  # noqa: E402
from unstract.sdk1.utils.image_limits import policy as policy_mod  # noqa: E402

BEDROCK_CFG = {
    "adapter_id": "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064",
    "adapter_metadata": {
        "model": "anthropic.claude-sonnet-4-5-20250929-v1:0",
        "aws_region_name": "us-east-1",
    },
}
OPENAI_CFG = {
    "adapter_id": "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
    "adapter_metadata": {
        "model": "gpt-5.6",
        "api_key": "k",
        "api_base": "https://api.openai.com/v1",
    },
}


def _resolver(configs: dict[str, dict | None]):
    def _get(_shim, adapter_instance_id):
        value = configs[adapter_instance_id]
        if isinstance(value, Exception):
            raise value
        return value

    return _get


@pytest.fixture(autouse=True)
def _no_env_ceilings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VLM_IMAGE_ANSWER_PAGE_CAP", raising=False)
    monkeypatch.delenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", raising=False)


class TestBuildExtractionImagePolicy:
    def test_resolves_each_llm_and_takes_the_strictest(self) -> None:
        with patch.object(
            exec_limits.PlatformHelper,
            "get_adapter_config",
            side_effect=_resolver({"llm-a": OPENAI_CFG, "llm-b": BEDROCK_CFG}),
        ):
            policy = exec_limits.build_extraction_image_policy(
                MagicMock(), ["llm-a", "llm-b"]
            )
        assert policy.model_aware is True
        assert policy.page_budget.max_pages == 20
        assert policy.page_budget.limits.provider_key == "bedrock"

    def test_legacy_bound_holds_generous_models_at_90_during_rollout(self) -> None:
        with patch.object(
            exec_limits.PlatformHelper,
            "get_adapter_config",
            side_effect=_resolver({"llm-a": OPENAI_CFG}),
        ):
            policy = exec_limits.build_extraction_image_policy(MagicMock(), ["llm-a"])
        assert policy.page_budget.max_pages == 90
        assert policy.bytes_ceiling == 14 * 1024 * 1024

    def test_without_the_legacy_bound_generous_models_go_above_90(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(policy_mod, "LEGACY_ANSWER_BOUNDS_ACTIVE", False)
        with patch.object(
            exec_limits.PlatformHelper,
            "get_adapter_config",
            side_effect=_resolver({"llm-a": OPENAI_CFG}),
        ):
            policy = exec_limits.build_extraction_image_policy(MagicMock(), ["llm-a"])
        assert policy.page_budget.max_pages > 90

    def test_duplicate_ids_are_resolved_once(self) -> None:
        with patch.object(
            exec_limits.PlatformHelper,
            "get_adapter_config",
            side_effect=_resolver({"llm-a": BEDROCK_CFG}),
        ) as get:
            exec_limits.build_extraction_image_policy(MagicMock(), ["llm-a", "llm-a", ""])
        assert get.call_count == 1

    def test_no_ids_means_ceiling_only_with_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with patch.object(exec_limits.PlatformHelper, "get_adapter_config") as get:
            policy = exec_limits.build_extraction_image_policy(MagicMock(), [])
        get.assert_not_called()
        assert policy.model_aware is False
        assert policy.page_budget.max_pages == 90  # legacy bound during rollout
        assert any("LLM" in rec.message for rec in caplog.records)

    @pytest.mark.parametrize(
        "failure",
        [
            None,
            RuntimeError("platform service down"),
            {"adapter_id": "nope|1", "adapter_metadata": {}},
        ],
    )
    def test_resolution_failure_fails_closed_before_conversion(self, failure) -> None:
        with patch.object(
            exec_limits.PlatformHelper,
            "get_adapter_config",
            side_effect=_resolver({"llm-a": failure}),
        ):
            with pytest.raises(ExtractionError) as excinfo:
                exec_limits.build_extraction_image_policy(MagicMock(), ["llm-a"])
        err = excinfo.value
        assert err.message.startswith(f"{codes.IMAGE_LIMITS_UNRESOLVED}: ")
        assert "No pages were converted or charged" in err.message
        assert err.code == 503


def _extract_context(params: dict) -> ExecutionContext:
    return ExecutionContext(
        executor_name="legacy",
        operation="extract",
        run_id="run-1",
        execution_source="ide",
        executor_params=params,
    )


def _x2text(*, image_mode: bool, process_side_effect=None):
    instance = MagicMock(spec=LLMWhispererV2)
    instance.config = {"output_mode": "image" if image_mode else "layout_preserving"}
    instance.get_name.return_value = "LLMWhisperer"
    x2text = MagicMock(name="X2Text")
    x2text.x2text_instance = instance
    result = MagicMock()
    result.extracted_text = "summary"
    result.extraction_metadata = None
    x2text.process.return_value = result
    if process_side_effect is not None:
        x2text.process.side_effect = process_side_effect
    return x2text


def _run_extract(x2text, params: dict, policy=None):
    executor = LegacyExecutor()
    base = {
        IKeys.X2TEXT_INSTANCE_ID: "x2t-1",
        IKeys.FILE_PATH: "/data/doc.pdf",
        IKeys.OUTPUT_FILE_PATH: "/data/extract/doc.txt",
        "platform_api_key": "k",
    }
    base.update(params)
    build = MagicMock(return_value=policy)
    with (
        patch("executor.executors.legacy_executor.X2Text", return_value=x2text),
        patch("executor.executors.legacy_executor.FileUtils.get_fs_instance"),
        patch.object(LegacyExecutor, "_build_shim", return_value=MagicMock()),
        patch("executor.executors.legacy_executor.build_extraction_image_policy", build),
    ):
        result = executor._handle_extract(_extract_context(base))
    return result, build


class TestHandleExtractWiring:
    def test_image_mode_passes_the_policy_to_the_adapter(self) -> None:
        policy = ImageModePolicy.ceiling_only(page_ceiling=7)
        x2text = _x2text(image_mode=True)
        result, build = _run_extract(
            x2text, {IKeys.LLM_INSTANCE_IDS: ["llm-1"]}, policy=policy
        )
        assert result.success
        build.assert_called_once()
        assert build.call_args.args[1] == ["llm-1"]
        assert x2text.process.call_args.kwargs[X2TextConstants.IMAGE_LIMITS] is policy

    def test_text_mode_never_resolves_limits(self) -> None:
        x2text = _x2text(image_mode=False)
        result, build = _run_extract(x2text, {IKeys.LLM_INSTANCE_IDS: ["llm-1"]})
        assert result.success
        build.assert_not_called()
        assert X2TextConstants.IMAGE_LIMITS not in x2text.process.call_args.kwargs

    def test_missing_ids_still_build_a_policy(self) -> None:
        policy = ImageModePolicy.ceiling_only()
        x2text = _x2text(image_mode=True)
        _, build = _run_extract(x2text, {}, policy=policy)
        assert build.call_args.args[1] == []

    def test_unresolved_limits_stop_before_conversion(self) -> None:
        x2text = _x2text(image_mode=True)
        executor = LegacyExecutor()
        with (
            patch("executor.executors.legacy_executor.X2Text", return_value=x2text),
            patch("executor.executors.legacy_executor.FileUtils.get_fs_instance"),
            patch.object(LegacyExecutor, "_build_shim", return_value=MagicMock()),
            patch(
                "executor.executors.legacy_executor.build_extraction_image_policy",
                side_effect=ExtractionError(
                    message="IMAGE_LIMITS_UNRESOLVED: x", code=503
                ),
            ),
        ):
            with pytest.raises(ExtractionError):
                executor._handle_extract(
                    _extract_context(
                        {
                            IKeys.X2TEXT_INSTANCE_ID: "x2t-1",
                            IKeys.FILE_PATH: "/data/doc.pdf",
                            IKeys.LLM_INSTANCE_IDS: ["llm-1"],
                        }
                    )
                )
        x2text.process.assert_not_called()


class TestExtractionErrorCodes:
    def test_limit_errors_keep_their_code_and_status(self) -> None:
        err = ImageLimitExceededError(
            "This document has 25 pages.",
            error_code=codes.IMAGE_PAGE_CAP_EXCEEDED,
            charged=False,
        )
        x2text = _x2text(image_mode=True, process_side_effect=err)
        with pytest.raises(ExtractionError) as excinfo:
            _run_extract(x2text, {}, policy=ImageModePolicy.ceiling_only())
        assert excinfo.value.message.startswith(
            f"{codes.IMAGE_PAGE_CAP_EXCEEDED}: Error from text extractor"
        )
        assert excinfo.value.code == 400

    def test_other_extractor_errors_are_unchanged(self) -> None:
        x2text = _x2text(image_mode=False, process_side_effect=ExtractorError("boom"))
        with pytest.raises(ExtractionError) as excinfo:
            _run_extract(x2text, {})
        assert excinfo.value.message == "Error from text extractor 'LLMWhisperer'. boom"
