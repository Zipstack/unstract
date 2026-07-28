"""Tests for the OSS vlm_image_answer bridge (detection + dispatch).

The bridge must: detect image mode from the resolved x2text adapter
config (never from payload metadata, which doesn't exist), raise a
structured plugin-absent error instead of falling through to the text
path, map sdk1 loader errors to stable error codes, and return None for
non-image adapters so the normal path continues untouched.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from executor.executors.exceptions import VlmImageAnswerError  # noqa: E402
from executor.executors.vlm_image_answer import (  # noqa: E402
    _MODE_CACHE,
    IMAGE_OUTPUT_MISSING,
    IMAGE_OUTPUT_REQUIRES_CLOUD,
    IMAGE_OUTPUT_UNSUPPORTED_OPERATION,
    IMAGE_PAGE_CAP_EXCEEDED,
    raise_if_image_mode_unsupported,
    run_vlm_image_answer,
)

from unstract.sdk1.adapters.x2text.page_image_loader import (  # noqa: E402
    PageCapExceededError,
    PageImagesNotFoundError,
)

_IMAGE_CONFIG = {
    "adapter_id": "llmwhisperer|0a1647f0-f65f-410d-843b-3d979c78350e",
    "adapter_metadata": {"output_mode": "image", "url": "http://svc"},
}
_TEXT_CONFIG = {
    "adapter_id": "llmwhisperer|0a1647f0-f65f-410d-843b-3d979c78350e",
    "adapter_metadata": {"output_mode": "layout_preserving"},
}
_OTHER_ADAPTER_CONFIG = {
    "adapter_id": "someocr|123",
    "adapter_metadata": {"output_mode": "image"},
}


@pytest.fixture(autouse=True)
def _clear_cache():
    _MODE_CACHE.clear()
    yield
    _MODE_CACHE.clear()


def _call(output=None, plugin=None, adapter_config=_IMAGE_CONFIG, **overrides):
    output = output or {"x2text_adapter": "uuid-1", "name": "p1", "promptx": "q?"}
    kwargs = {
        "output": output,
        "shim": MagicMock(),
        "llm": MagicMock(),
        "file_path": "/data/extract/doc.txt",
        "execution_source": "ide",
        "metadata": {"context": {}},
        "metrics": {},
        "usage_kwargs": {"run_id": "r1", "execution_id": "e1"},
    }
    kwargs.update(overrides)
    with (
        patch(
            "executor.executors.vlm_image_answer.PlatformHelper.get_adapter_config",
            return_value=adapter_config,
        ),
        patch(
            "executor.executors.vlm_image_answer.ExecutorPluginLoader.get",
            return_value=plugin,
        ),
        patch(
            "executor.executors.vlm_image_answer.FileUtils.get_fs_instance",
            return_value=MagicMock(),
        ),
    ):
        return run_vlm_image_answer(**kwargs)


class TestDetection:
    def test_non_image_mode_returns_none(self):
        assert _call(adapter_config=_TEXT_CONFIG) is None

    def test_non_llmwhisperer_adapter_returns_none(self):
        # Another adapter with a coincidental output_mode key is not gated.
        assert _call(adapter_config=_OTHER_ADAPTER_CONFIG) is None

    def test_missing_adapter_id_returns_none_without_platform_call(self):
        with patch(
            "executor.executors.vlm_image_answer.PlatformHelper.get_adapter_config"
        ) as resolve:
            result = run_vlm_image_answer(
                output={"name": "p1"},
                shim=MagicMock(),
                llm=MagicMock(),
                file_path="/f.txt",
                execution_source="ide",
                metadata={},
                metrics={},
            )
        assert result is None
        resolve.assert_not_called()

    def test_resolution_cached_per_execution_and_adapter(self):
        plugin = MagicMock()
        plugin.run_with_metrics.return_value = {"answer": "a"}
        with (
            patch(
                "executor.executors.vlm_image_answer.PlatformHelper.get_adapter_config",
                return_value=_IMAGE_CONFIG,
            ) as resolve,
            patch(
                "executor.executors.vlm_image_answer.ExecutorPluginLoader.get",
                return_value=plugin,
            ),
            patch(
                "executor.executors.vlm_image_answer.FileUtils.get_fs_instance",
                return_value=MagicMock(),
            ),
        ):
            common = {
                "shim": MagicMock(),
                "llm": MagicMock(),
                "file_path": "/data/extract/doc.txt",
                "execution_source": "ide",
                "metadata": {"context": {}},
                "metrics": {},
                "usage_kwargs": {"execution_id": "e1"},
            }
            for _ in range(3):  # three prompts, same adapter + execution
                run_vlm_image_answer(
                    output={"x2text_adapter": "uuid-1", "name": "p"}, **common
                )
        assert resolve.call_count == 1


class TestPluginAbsent:
    def test_raises_structured_error_never_falls_through(self):
        with pytest.raises(VlmImageAnswerError) as excinfo:
            _call(plugin=None)
        assert excinfo.value.error_code == IMAGE_OUTPUT_REQUIRES_CLOUD
        assert str(excinfo.value).startswith(IMAGE_OUTPUT_REQUIRES_CLOUD + ":")
        assert "Unstract Cloud" in str(excinfo.value)


class TestPluginDispatch:
    def test_answer_and_page_store_dir_contract(self):
        plugin = MagicMock()
        plugin.run_with_metrics.return_value = {"answer": "42", "llm_metrics": {"t": 1}}
        metrics = {}
        answer = _call(plugin=plugin, metrics=metrics)
        assert answer == "42"
        call_kwargs = plugin.run_with_metrics.call_args.kwargs
        # Deterministic path derived from the extract file path via the
        # shared helper — the writer/reader agreement contract.
        assert call_kwargs["page_store_dir"] == "/data/extract/doc/pages"
        assert call_kwargs["x2text_config"] == _IMAGE_CONFIG
        assert metrics["p1"]["vlm_image_answer"] == {"t": 1}

    def test_loader_not_found_maps_to_image_output_missing(self):
        plugin = MagicMock()
        plugin.run_with_metrics.side_effect = PageImagesNotFoundError(
            "no images", page_store_dir="/d/pages"
        )
        with pytest.raises(VlmImageAnswerError) as excinfo:
            _call(plugin=plugin)
        assert excinfo.value.error_code == IMAGE_OUTPUT_MISSING

    def test_cap_error_maps_to_page_cap_code(self):
        plugin = MagicMock()
        plugin.run_with_metrics.side_effect = PageCapExceededError(
            "too big", page_store_dir="/d/pages", page_count=50, page_cap=20
        )
        with pytest.raises(VlmImageAnswerError) as excinfo:
            _call(plugin=plugin)
        assert excinfo.value.error_code == IMAGE_PAGE_CAP_EXCEEDED

    def test_plugin_error_code_attribute_is_wrapped(self):
        class VisionError(Exception):
            error_code = "VISION_LLM_REQUIRED"

        plugin = MagicMock()
        plugin.run_with_metrics.side_effect = VisionError("model X has no vision")
        with pytest.raises(VlmImageAnswerError) as excinfo:
            _call(plugin=plugin)
        assert excinfo.value.error_code == "VISION_LLM_REQUIRED"
        assert "model X has no vision" in str(excinfo.value)

    def test_unexpected_plugin_error_propagates_unwrapped(self):
        plugin = MagicMock()
        plugin.run_with_metrics.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            _call(plugin=plugin)


class TestUnsupportedOperationGuard:
    def test_single_pass_rejected_for_image_mode(self):
        with patch(
            "executor.executors.vlm_image_answer.PlatformHelper.get_adapter_config",
            return_value=_IMAGE_CONFIG,
        ):
            with pytest.raises(VlmImageAnswerError) as excinfo:
                raise_if_image_mode_unsupported(
                    operation="Single-pass extraction",
                    adapter_instance_id="uuid-1",
                    shim=MagicMock(),
                    execution_id="e1",
                )
        assert excinfo.value.error_code == IMAGE_OUTPUT_UNSUPPORTED_OPERATION

    def test_text_mode_passes(self):
        with patch(
            "executor.executors.vlm_image_answer.PlatformHelper.get_adapter_config",
            return_value=_TEXT_CONFIG,
        ):
            raise_if_image_mode_unsupported(
                operation="Single-pass extraction",
                adapter_instance_id="uuid-1",
                shim=MagicMock(),
                execution_id="e1",
            )  # no raise

    def test_no_adapter_id_passes(self):
        raise_if_image_mode_unsupported(
            operation="Single-pass extraction",
            adapter_instance_id=None,
            shim=MagicMock(),
        )  # no raise, no platform call
