"""Tests for the OSS vlm_utils bridge (no-op without the cloud package).

Mirrors the lookup_utils bridge contract: every helper degrades safely
in OSS, delegates when the cloud hooks module is present, and the
non-critical hooks (warning, invalidation) never let a cloud-side
failure break the OSS operation they ride on.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from _pytest.monkeypatch import MonkeyPatch

from prompt_studio import vlm_utils


class TestOssNoOps:
    def test_cloud_package_absent_in_oss(self) -> None:
        assert vlm_utils.VLM_IMAGE_ANSWER_AVAILABLE is False

    def test_hooks_not_marked_broken_in_oss(self) -> None:
        # Package absent is the expected OSS state — it must not be
        # conflated with the fail-closed "installed but broken" state.
        assert vlm_utils.VLM_HOOKS_BROKEN is False

    def test_vision_warning_is_none(self) -> None:
        assert vlm_utils.get_profile_vision_warning(SimpleNamespace()) is None

    def test_deployment_validation_is_noop(self) -> None:
        vlm_utils.validate_workflow_for_deployment(SimpleNamespace())  # no raise

    def test_invalidation_is_noop(self) -> None:
        vlm_utils.invalidate_vlm_answers_on_reextraction(
            document_id="d1",
            profile_manager=SimpleNamespace(),
            extract_file_path="/x/extract/doc.txt",
        )  # no raise


@pytest.fixture
def cloud_hooks(monkeypatch: MonkeyPatch) -> MagicMock:
    hooks = MagicMock()
    monkeypatch.setattr(vlm_utils, "_hooks", hooks)
    monkeypatch.setattr(vlm_utils, "VLM_IMAGE_ANSWER_AVAILABLE", True)
    return hooks


class TestCloudDelegation:
    def test_vision_warning_delegates(self, cloud_hooks: MagicMock) -> None:
        cloud_hooks.get_profile_vision_warning.return_value = "warn!"
        assert vlm_utils.get_profile_vision_warning(SimpleNamespace()) == "warn!"

    def test_vision_warning_failure_swallowed(self, cloud_hooks: MagicMock) -> None:
        # A warning must never break profile save/read.
        cloud_hooks.get_profile_vision_warning.side_effect = RuntimeError("x")
        assert vlm_utils.get_profile_vision_warning(SimpleNamespace()) is None

    def test_deployment_validation_propagates(self, cloud_hooks: MagicMock) -> None:
        # Deploy-time rejection is a hard gate — errors must propagate.
        cloud_hooks.validate_workflow_for_deployment.side_effect = ValueError("no")
        with pytest.raises(ValueError):
            vlm_utils.validate_workflow_for_deployment(SimpleNamespace())

    def test_invalidation_delegates_and_swallows_failure(
        self, cloud_hooks: MagicMock
    ) -> None:
        profile = SimpleNamespace()
        vlm_utils.invalidate_vlm_answers_on_reextraction(
            document_id="d1", profile_manager=profile, extract_file_path="/e.txt"
        )
        cloud_hooks.invalidate_vlm_answers_on_reextraction.assert_called_once_with(
            document_id="d1", profile_manager=profile, extract_file_path="/e.txt"
        )
        # Invalidation failure must not fail the extraction it rides on.
        cloud_hooks.invalidate_vlm_answers_on_reextraction.side_effect = RuntimeError
        vlm_utils.invalidate_vlm_answers_on_reextraction(
            document_id="d1", profile_manager=profile, extract_file_path="/e.txt"
        )  # no raise
