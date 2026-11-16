"""Tests for vision-capability detection and the image-mode gating policy.

Registry lookups are exercised against a controlled fake of
``litellm.model_cost`` so results don't drift with litellm releases; a
couple of smoke tests hit the real registry for stable, long-lived models.
"""

import pytest
from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.utils import vision_capability as vc
from unstract.sdk1.utils.vision_capability import (
    VisionSupport,
    check_vision_support,
    validate_vision_capability,
)

_FAKE_REGISTRY = {
    "vision-model": {"supports_vision": True},
    "provider/prefixed-vision": {"supports_vision": True},
    "text-only-model": {"litellm_provider": "x"},  # known, no vision flag
    "explicit-no-vision": {"supports_vision": False},
}


@pytest.fixture
def fake_registry(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(vc.litellm, "model_cost", _FAKE_REGISTRY)


class TestCheckVisionSupport:
    def test_known_vision_model(self, fake_registry: None) -> None:
        assert check_vision_support("vision-model") is VisionSupport.SUPPORTED

    def test_prefix_stripped_lookup(self, fake_registry: None) -> None:
        # Registry keyed without the provider prefix still resolves.
        assert check_vision_support("provider/prefixed-vision") is (
            VisionSupport.SUPPORTED
        )

    def test_known_model_without_flag_is_unsupported(self, fake_registry: None) -> None:
        # In the registry, absence of supports_vision on a KNOWN model is
        # authoritative "no vision" (litellm omits the key rather than
        # setting False).
        assert check_vision_support("text-only-model") is VisionSupport.UNSUPPORTED

    def test_explicit_false_is_unsupported(self, fake_registry: None) -> None:
        assert check_vision_support("explicit-no-vision") is VisionSupport.UNSUPPORTED

    def test_unregistered_model_is_unknown(self, fake_registry: None) -> None:
        assert check_vision_support("ollama/llava") is VisionSupport.UNKNOWN

    def test_empty_model_is_unknown(self, fake_registry: None) -> None:
        assert check_vision_support("") is VisionSupport.UNKNOWN

    def test_no_network_calls_ever(self, monkeypatch: MonkeyPatch) -> None:
        # get_model_info can hit the network for self-hosted providers —
        # classification must never call it.
        monkeypatch.setattr(
            vc.litellm,
            "get_model_info",
            lambda *a, **k: pytest.fail("get_model_info must not be called"),
            raising=False,
        )
        check_vision_support("ollama/anything")
        check_vision_support("gpt-4o")


class TestPolicy:
    def test_supported_allows_silently(self, fake_registry: None) -> None:
        result = validate_vision_capability("vision-model")
        assert result.allowed is True
        assert result.message is None

    def test_unknown_warns_and_allows(self, fake_registry: None) -> None:
        result = validate_vision_capability("ollama/custom-vlm")
        assert result.allowed is True
        assert result.support is VisionSupport.UNKNOWN
        assert result.message and "cannot be verified" in result.message

    def test_unsupported_blocks_and_names_model(self, fake_registry: None) -> None:
        result = validate_vision_capability("text-only-model")
        assert result.allowed is False
        assert "text-only-model" in result.message
        assert "vision-capable" in result.message


class TestRealRegistrySmoke:
    """Long-stable models against the real litellm registry."""

    def test_gpt_4o_supported(self) -> None:
        assert check_vision_support("gpt-4o") is VisionSupport.SUPPORTED

    def test_gpt_35_turbo_unsupported(self) -> None:
        assert check_vision_support("gpt-3.5-turbo") is VisionSupport.UNSUPPORTED

    def test_fabricated_model_unknown(self) -> None:
        assert check_vision_support("no-such/model-xyz-123") is VisionSupport.UNKNOWN
