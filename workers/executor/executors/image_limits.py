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
fixed 90-page / 14 MiB cap (``ImageModePolicy.fixed_cap``), the pre-UN-4427
behaviour. sdk1's builders honour the switch too; checking it here first
also skips the adapter lookups, which could otherwise fail closed.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from executor.executors.exceptions import ExtractionError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.llm import LLM
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.utils.image_limits import (
    ENFORCE_ENV,
    ImageModePolicy,
    codes,
    extraction_bound_kwargs,
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


def _is_transient(error: BaseException) -> bool:
    """True for a lookup failure a retry can fix: no connection, a timeout, a 5xx.

    ``PlatformHelper.get_adapter_config`` wraps most failures in ``SdkError``
    (a refused connection, a 4xx), so the cause chain is inspected. Anything
    else (a 4xx such as an unknown or forbidden adapter, a bad public
    adapter definition) is deterministic: retrying returns the same error.
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current,
            (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError),
        ):
            return True
        if isinstance(current, requests.HTTPError):
            response = current.response
            return response is not None and response.status_code >= 500
        current = current.__cause__ or current.__context__
    return False


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
        return ImageModePolicy.fixed_cap()
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
                llm_instance_id, str(e) or type(e).__name__, transient=_is_transient(e)
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
