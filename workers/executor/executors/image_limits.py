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
"""

from __future__ import annotations

import logging
from typing import Any

from executor.executors.exceptions import ExtractionError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.llm import LLM
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.utils.image_limits import (
    ImageModePolicy,
    codes,
    extraction_bound_kwargs,
)

logger = logging.getLogger(__name__)

# Retryable: the failure is ours (platform service, adapter config), not the
# document's, and nothing was converted or charged.
_UNRESOLVED_STATUS = 503


def _unresolved(llm_instance_id: str, reason: str) -> ExtractionError:
    return ExtractionError(
        message=(
            f"{codes.IMAGE_LIMITS_UNRESOLVED}: Could not look up the image limits "
            f"of the LLM (adapter {llm_instance_id}) that will read this document: "
            f"{reason}. No pages were converted or charged; retry, or check the "
            "profile's LLM adapter."
        ),
        code=_UNRESOLVED_STATUS,
    )


def build_extraction_image_policy(
    shim: Any, llm_instance_ids: list[str] | tuple[str, ...]
) -> ImageModePolicy:
    """The policy for an image-mode extraction consumed by ``llm_instance_ids``."""
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
            raise _unresolved(llm_instance_id, str(e) or type(e).__name__) from e
        if not config:
            raise _unresolved(llm_instance_id, "the adapter configuration is missing")
        try:
            limits, tokens = LLM.image_input_limits_for(
                config[Common.ADAPTER_ID], config[Common.ADAPTER_METADATA] or {}
            )
        except Exception as e:
            raise _unresolved(llm_instance_id, str(e) or type(e).__name__) from e
        resolved.append(limits)
        token_budgets.append(tokens)

    policy = ImageModePolicy.from_limits(resolved, token_budgets=token_budgets, **bounds)
    logger.info("Image mode: %s", policy.describe())
    return policy
