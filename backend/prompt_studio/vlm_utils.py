"""Bridge helpers for the cloud-only VLM image-answer feature. No-ops in OSS.

Image output mode is answered by a vision LLM through the cloud-only
``vlm-image-answer`` plugin. The backend touch points below (profile-save
vision warning, deploy-time validation, answer-cache invalidation on
re-extraction) delegate to ``plugins.vlm_image_answer.backend_hooks`` when
that cloud package is present and degrade to no-ops when it is not — OSS
additionally hides the image output mode entirely via
``adapter_processor_v2.image_output_gating``.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from plugins.vlm_image_answer import backend_hooks as _hooks

    VLM_IMAGE_ANSWER_AVAILABLE = True
except ImportError:
    _hooks = None
    VLM_IMAGE_ANSWER_AVAILABLE = False


def get_profile_vision_warning(profile_manager: Any) -> str | None:
    """Non-blocking warning when an image-mode profile's LLM lacks vision.

    Returns a human-readable warning string, or None (always None in OSS).
    Never raises — a warning must not break profile save/read.
    """
    if not VLM_IMAGE_ANSWER_AVAILABLE:
        return None
    try:
        return _hooks.get_profile_vision_warning(profile_manager)
    except Exception:
        logger.exception("VLM vision warning check failed; skipping warning")
        return None


def validate_workflow_for_deployment(workflow: Any) -> None:
    """Deploy-time guard: reject deployments that cannot serve image mode.

    The cloud hook raises ``rest_framework.serializers.ValidationError``
    for a definitive misconfiguration (e.g. image-mode profile with a
    known non-vision LLM); OSS is a no-op (image mode is gated off).
    """
    if not VLM_IMAGE_ANSWER_AVAILABLE:
        return
    _hooks.validate_workflow_for_deployment(workflow)


def invalidate_vlm_answers_on_reextraction(
    document_id: str, profile_manager: Any, extract_file_path: str
) -> None:
    """Invalidate stored VLM answers after a re-extraction rewrote pages/.

    Called from the extraction choke point right after a successful
    (non-cache-hit) extraction. Never raises — invalidation failure must
    not fail the extraction itself; the cloud hook logs and degrades.
    """
    if not VLM_IMAGE_ANSWER_AVAILABLE:
        return
    try:
        _hooks.invalidate_vlm_answers_on_reextraction(
            document_id=document_id,
            profile_manager=profile_manager,
            extract_file_path=extract_file_path,
        )
    except Exception:
        logger.exception("VLM answer invalidation failed after re-extraction")
