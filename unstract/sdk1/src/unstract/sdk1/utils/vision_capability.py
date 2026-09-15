"""Vision-capability detection and gating policy for LLM models.

The image output mode sends page images to the profile's LLM via
``complete_vision``; a non-vision model fails only at run time with an
opaque provider error. This module classifies a model's vision support
up front and applies the gating policy shared by config-time warnings
and run-time guards.

Classification uses LiteLLM's **local** ``model_cost`` registry only —
never ``get_model_info`` — because ``get_model_info`` can make network
calls for self-hosted providers (e.g. it queries the Ollama server), and
``litellm.supports_vision`` alone returns ``False`` for both known
non-vision models *and* unknown models, which would wrongly hard-block
custom/self-hosted vision models (LiteLLM proxies, Ollama).

Policy (locked): hard-block only on a **definitive** "known model, no
vision support"; unknown/custom models are allowed with a warning — the
provider's own runtime error remains the backstop.
"""

import logging
from dataclasses import dataclass
from enum import Enum

import litellm

logger = logging.getLogger(__name__)


class VisionSupport(Enum):
    """Classification of a model's vision (image input) capability."""

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VisionValidationResult:
    """Outcome of applying the gating policy to a model."""

    model: str
    support: VisionSupport
    allowed: bool
    message: str | None


def check_vision_support(model: str) -> VisionSupport:
    """Classify ``model``'s vision capability from the local registry.

    The registry is keyed both with and without provider prefixes
    (``anthropic/claude-…`` vs ``claude-…``); a model found under either
    form is "known". On known models the ``supports_vision`` flag is
    authoritative — absence means no vision support. Models not in the
    registry (self-hosted, proxies, brand-new releases) are UNKNOWN.
    """
    if not model:
        return VisionSupport.UNKNOWN
    registry = litellm.model_cost
    entry = registry.get(model)
    if entry is None and "/" in model:
        entry = registry.get(model.split("/", 1)[-1])
    if entry is None:
        return VisionSupport.UNKNOWN
    if entry.get("supports_vision"):
        return VisionSupport.SUPPORTED
    return VisionSupport.UNSUPPORTED


def validate_vision_capability(model: str) -> VisionValidationResult:
    """Apply the image-mode gating policy to ``model``.

    Returns a result rather than raising so callers can map it to their
    own error/warning surfaces (structured API errors, profile-save
    warnings). ``allowed`` is False only for a definitive UNSUPPORTED.
    """
    support = check_vision_support(model)
    if support is VisionSupport.SUPPORTED:
        return VisionValidationResult(
            model=model, support=support, allowed=True, message=None
        )
    if support is VisionSupport.UNKNOWN:
        message = (
            f"Model '{model}' is not in the capability registry, so its "
            "image (vision) support cannot be verified. The run will "
            "proceed; if the model does not accept image input, the "
            "provider will reject the request."
        )
        logger.warning(message)
        return VisionValidationResult(
            model=model, support=support, allowed=True, message=message
        )
    return VisionValidationResult(
        model=model,
        support=support,
        allowed=False,
        message=(
            f"Model '{model}' does not support image input. Image output "
            "mode requires a vision-capable LLM — update this profile's "
            "LLM to a vision model (e.g. a GPT-4o, Claude, or Gemini "
            "vision model) and re-run."
        ),
    )
