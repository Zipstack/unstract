"""Resolve the image-request limits that apply to one image-mode extraction.

Image output mode sends every page image to the consuming LLM in one
request, and LLMWhisperer bills the page conversion before the pages can be
measured. The extraction therefore has to know the LLM's limits up front,
but the x2text adapter only knows the text extractor: the caller passes the
LLM adapter instance ids (the profile's LLM in Prompt Studio, every prompt's
LLM for a deployment) and this module resolves them into one
``ImageModePolicy`` (the strictest of each limit wins).

Fail closed: when ids are supplied but cannot be resolved, the extraction
stops before conversion with ``IMAGE_LIMITS_UNRESOLVED`` rather than billing
a conversion that may be unanswerable. With no ids at all (pre-upgrade
payloads), only the platform ceilings apply and answer time re-checks.

``VLM_IMAGE_LIMITS_ENFORCE=false`` skips the LLM lookup and applies the
fixed 90-page / 14 MiB cap (``ceiling_only``), the pre-UN-4427 behaviour.
"""

from __future__ import annotations

import logging
from typing import Any

from executor.executors.exceptions import ExtractionError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.llm import LLM
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.utils.image_limits import (
    ENFORCE_ENV,
    ImageModePolicy,
    codes,
    extraction_bound_kwargs,
    fixed_cap_bound_kwargs,
    model_aware_limits_enabled,
)

logger = logging.getLogger(__name__)

# The status is informational: the executor returns only the message. The
# advice in the message is what tells the user whether retrying can help.
_TRANSIENT_STATUS = 503  # the platform service lookup failed
_CONFIG_STATUS = 400  # the adapter configuration itself is unusable


def _unresolved(llm_instance_id: str, reason: str, *, transient: bool) -> ExtractionError:
    advice = (
        "retry in a moment; the adapter lookup failed"
        if transient
        else "fix the profile's LLM adapter configuration or pick another LLM; "
        "retrying will not help"
    )
    return ExtractionError(
        message=(
            f"{codes.IMAGE_LIMITS_UNRESOLVED}: Could not look up the image limits "
            f"of the LLM (adapter {llm_instance_id}) that will read this document: "
            f"{reason}. No pages were converted or charged; {advice}."
        ),
        code=_TRANSIENT_STATUS if transient else _CONFIG_STATUS,
    )


def build_extraction_image_policy(
    shim: Any, llm_instance_ids: list[str] | tuple[str, ...]
) -> ImageModePolicy:
    """The policy for an image-mode extraction consumed by ``llm_instance_ids``."""
    if not model_aware_limits_enabled():
        logger.warning(
            "Image mode: %s=false; applying the fixed page and byte cap instead "
            "of the LLM's limits",
            ENFORCE_ENV,
        )
        return ImageModePolicy.ceiling_only(**fixed_cap_bound_kwargs())
    bounds = extraction_bound_kwargs()
    ids = list(dict.fromkeys(str(i) for i in llm_instance_ids if i))
    if not ids:
        logger.warning(
            "Image mode: no LLM adapter ids supplied with the extraction; only "
            "platform ceilings apply before conversion (the answer step "
            "re-checks against the LLM)"
        )
        return ImageModePolicy.ceiling_only(**bounds)

    resolved = []
    token_budgets = []
    for llm_instance_id in ids:
        try:
            config = PlatformHelper.get_adapter_config(shim, llm_instance_id)
        except Exception as e:
            raise _unresolved(
                llm_instance_id, str(e) or type(e).__name__, transient=True
            ) from e
        if not config:
            raise _unresolved(
                llm_instance_id, "the adapter configuration is missing", transient=False
            )
        try:
            limits, tokens = LLM.image_input_limits_for(
                config[Common.ADAPTER_ID], config[Common.ADAPTER_METADATA] or {}
            )
        except Exception as e:
            raise _unresolved(
                llm_instance_id, str(e) or type(e).__name__, transient=False
            ) from e
        resolved.append(limits)
        token_budgets.append(tokens)

    policy = ImageModePolicy.from_limits(resolved, token_budgets=token_budgets, **bounds)
    logger.info("Image mode: %s", policy.describe())
    return policy
