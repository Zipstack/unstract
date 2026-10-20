"""Turn resolved image limits into the checks image output mode enforces.

Three ceilings bound how many page images one request can carry: the
provider's image count, the model's context window (estimated from a
per-page token figure) and LLMWhisperer's 999-page conversion maximum,
plus optional operator ceilings. ``compute_page_budget`` picks the
binding one and remembers why, so every error message can say which
limit the user hit and where the number came from.

Byte limits are only checkable once pages are rendered: ``ImageModePolicy``
converts a provider's wire limit (base64 JSON body) into a raw-byte budget
for the loader's bounded reads, and ``check_page_set`` applies the
per-image and whole-set checks to a page set in memory.

Pass-through providers (Ollama, OpenAI-compatible servers, NVIDIA Build,
unknown OpenRouter upstreams) publish no limits. Their count/byte values
come from the table's conservative default and are ADVISORY: the policy
logs what the default would have been instead of rejecting a document the
operator's server might well accept.

Tunables are module constants so a product decision is one edit.
"""

from __future__ import annotations

import dataclasses
import logging
import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from unstract.sdk1.adapters.x2text.constants import ImageOutputConstants
from unstract.sdk1.adapters.x2text.page_image_loader import (
    PageCapExceededError,
    PageImageSetTooLargeError,
    PageImageTooLargeError,
    configured_max_total_bytes,
    configured_page_cap,
    configured_page_ceiling,
    configured_request_bytes_ceiling,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from unstract.sdk1.utils.image_limits.resolve import ImageRequestLimits, LimitValue

logger = logging.getLogger(__name__)

# --- Tunables (product decisions; one edit each) -------------------------
# Tokens kept back from the context window for the prompt, system text and
# the answer when deriving the token-based page cap.
PROMPT_TOKENS_RESERVE = 4_000
# Reject when the estimated image tokens exceed the context window. The
# provider would reject the request anyway, after the full upload.
ENFORCE_CONTEXT_TOKEN_TERM = True
# Reject a page that breaks a per-image byte or pixel limit (no downscaling
# exists in this path).
ENFORCE_PER_IMAGE_LIMITS = True
# Wire bytes reserved for the prompt text when it is not known (extraction
# time), and per page for the "Page N" label and JSON framing.
TEXT_RESERVE_BYTES = 65_536
PAGE_LABEL_OVERHEAD_BYTES = 64
# Median raw size of a 150-DPI page PNG (354-PDF sample); used ONLY for the
# pre-conversion size advisory, never to reject.
ASSUMED_PAGE_BYTES = 250_000
# TEMPORARY rollout bound (UN-4427). The cloud vlm-image-answer plugin still
# answers with the fixed legacy limits (90 pages / 14 MiB, or their env
# overrides). Until it switches to model-aware limits, extraction is bounded
# by the same values so a document can never pass extraction (and be billed)
# and then be rejected at answer time by the plugin. Set to False — and
# delete with the legacy accessors — once the cloud change is released.
LEGACY_ANSWER_BOUNDS_ACTIVE = True
# base64 inflates 3 raw bytes to 4 characters.
_B64_NUM, _B64_DEN = 4, 3
_MB = 1_000_000  # the table's byte limits are decimal
_MIB = 1024 * 1024  # operator / legacy ceilings are MiB (VLM_IMAGE_ANSWER_MAX_TOTAL_MB)


def _mb(n: float) -> str:
    """Decimal megabytes, for provider limits (documented in MB)."""
    return f"{n / _MB:.1f} MB"


def _mib(n: float) -> str:
    """Mebibytes, for the operator and legacy ceilings (configured in MiB)."""
    return f"{n / _MIB:.1f} MiB"


# --- Bounds shared by every caller -------------------------------------------


def extraction_bound_kwargs() -> dict[str, int | None]:
    """Ceilings every image-mode policy applies on top of the model's limits.

    Operator ceilings (``VLM_IMAGE_ANSWER_PAGE_CAP`` /
    ``VLM_IMAGE_ANSWER_MAX_TOTAL_MB``) always apply; while
    ``LEGACY_ANSWER_BOUNDS_ACTIVE`` the legacy 90-page / 14 MiB answer-time
    limits are used instead, so extraction is never looser than the plugin.
    Pass the result to ``ImageModePolicy.from_limits`` / ``ceiling_only``.
    """
    if LEGACY_ANSWER_BOUNDS_ACTIVE:
        # The legacy accessors already fold the same env vars in.
        return {
            "page_ceiling": None,
            "bytes_ceiling": configured_max_total_bytes(),
            "legacy_cap": configured_page_cap(),
        }
    return {
        "page_ceiling": configured_page_ceiling(),
        "bytes_ceiling": configured_request_bytes_ceiling(),
        "legacy_cap": None,
    }


# --- Page budget -----------------------------------------------------------


@dataclass(frozen=True)
class PageBudget:
    """The effective page cap and the term that produced it."""

    max_pages: int
    binding: str  # images | tokens | llmwhisperer | ceiling | legacy
    limits: ImageRequestLimits | None
    context_tokens: int | None
    advisory_max_images: int | None
    terms: Mapping[str, int | None] = field(default_factory=dict)

    def describe(self) -> str:
        """One sentence naming the binding limit, for messages and logs."""
        limits = self.limits
        label = _model_label(limits) if limits else "this model"
        if self.binding == "images" and limits is not None:
            return (
                f"{label} accepts up to {self.max_pages} page images in one "
                "request ("
                + format_limit_source(
                    limits.max_images_per_request, limits, with_table_version=False
                )
                + ")"
            )
        if self.binding == "tokens" and limits is not None:
            per_page = limits.tokens_per_image.value or 0
            return (
                f"at about {per_page:,} tokens per page, the "
                f"{(self.context_tokens or 0):,}-token context window of {label} "
                f"fits at most {self.max_pages} pages"
            )
        if self.binding == "llmwhisperer":
            return f"LLMWhisperer converts at most {self.max_pages} pages of a document"
        if self.binding == "ceiling":
            return (
                f"the platform limit set by your administrator is {self.max_pages} pages"
            )
        return f"image output mode currently accepts at most {self.max_pages} pages"


def compute_page_budget(
    limits: ImageRequestLimits,
    *,
    context_tokens: int | None,
    prompt_tokens_reserve: int | None = None,
    page_ceiling: int | None = None,
    legacy_cap: int | None = None,
) -> PageBudget:
    """The smallest of the image-count, token, LLMWhisperer and ceiling terms.

    ``context_tokens`` is the caller's context-window figure (litellm, local
    registry); a ``max_input_tokens`` value in the table overrides it. An
    unknown context skips the token term rather than inventing a number.
    An advisory image count (pass-through provider on the default) is
    recorded but not applied.
    """
    reserve = (
        PROMPT_TOKENS_RESERVE if prompt_tokens_reserve is None else prompt_tokens_reserve
    )
    terms: dict[str, int | None] = {}

    count = limits.max_images_per_request
    advisory_count = count.value if count.advisory else None
    terms["images"] = None if count.advisory else count.value

    context = limits.max_input_tokens.value or context_tokens
    per_page = limits.tokens_per_image.value
    token_term: int | None = None
    if ENFORCE_CONTEXT_TOKEN_TERM and context and per_page:
        token_term = max((context - reserve) // per_page, 0)
    terms["tokens"] = token_term
    terms["llmwhisperer"] = ImageOutputConstants.LLMWHISPERER_MAX_PAGES
    terms["ceiling"] = page_ceiling
    terms["legacy"] = legacy_cap

    binding = "llmwhisperer"
    max_pages = ImageOutputConstants.LLMWHISPERER_MAX_PAGES
    # Order decides ties: a model limit equal to the ceiling is still the
    # model's limit, which is the more useful thing to tell the user.
    for name in ("images", "tokens", "llmwhisperer", "ceiling", "legacy"):
        value = terms[name]
        if value is not None and value < max_pages:
            max_pages, binding = value, name
    return PageBudget(
        max_pages=max_pages,
        binding=binding,
        limits=limits,
        context_tokens=context,
        advisory_max_images=advisory_count,
        terms=terms,
    )


# --- Policy ----------------------------------------------------------------


def _raw_equivalent(limit: LimitValue) -> int | None:
    if limit.value is None:
        return None
    return limit.value * _B64_DEN // _B64_NUM if limit.base64_counted else limit.value


def _min_limit(values: Iterable[LimitValue]) -> LimitValue | None:
    best: LimitValue | None = None
    for value in values:
        if value.value is None or value.advisory:
            continue
        if best is None or (_raw_equivalent(value) or 0) < (_raw_equivalent(best) or 0):
            best = value
    return best


@dataclass(frozen=True)
class ImageModePolicy:
    """Everything the extraction and answer paths need to check a page set."""

    page_budget: PageBudget
    request_bytes: LimitValue | None  # enforced wire/raw limit, if any
    advisory_request_bytes: LimitValue | None
    max_image_bytes: int | None
    max_image_bytes_base64_counted: bool
    max_image_px: int | None
    many_images_threshold: int | None
    many_images_max_px: int | None
    bytes_ceiling: int | None  # operator ceiling on raw bytes
    sources: tuple[ImageRequestLimits, ...]
    model_aware: bool

    @property
    def max_request_bytes(self) -> int | None:
        return self.request_bytes.value if self.request_bytes else None

    @classmethod
    def from_limits(
        cls,
        resolved: Sequence[ImageRequestLimits],
        *,
        token_budgets: Sequence[int | None] | None = None,
        page_ceiling: int | None = None,
        bytes_ceiling: int | None = None,
        legacy_cap: int | None = None,
    ) -> ImageModePolicy:
        """Build the policy for one or more LLMs (the strictest of each wins)."""
        if not resolved:
            raise ValueError("from_limits needs at least one resolved limit set")
        budgets_in = list(token_budgets or [None] * len(resolved))
        if len(budgets_in) != len(resolved):
            raise ValueError("token_budgets must align with resolved")
        budgets = [
            compute_page_budget(
                limits,
                context_tokens=tokens,
                page_ceiling=page_ceiling,
                legacy_cap=legacy_cap,
            )
            for limits, tokens in zip(resolved, budgets_in, strict=True)
        ]
        page_budget = min(budgets, key=lambda b: b.max_pages)

        request_bytes = _min_limit(lim.max_request_bytes for lim in resolved)
        advisory_bytes = next(
            (lim.max_request_bytes for lim in resolved if lim.max_request_bytes.advisory),
            None,
        )
        image_bytes = _min_limit(lim.max_image_bytes for lim in resolved)
        px_values = [lim.max_image_px.value for lim in resolved if lim.max_image_px.value]
        thresholds = [
            (lim.many_images_threshold.value, lim.many_images_max_px.value)
            for lim in resolved
            if lim.many_images_threshold.value and lim.many_images_max_px.value
        ]
        threshold = min((t for t, _ in thresholds), default=None)
        many_px = min((p for _, p in thresholds), default=None)
        return cls(
            page_budget=page_budget,
            request_bytes=request_bytes,
            advisory_request_bytes=advisory_bytes,
            max_image_bytes=_raw_equivalent(image_bytes) if image_bytes else None,
            max_image_bytes_base64_counted=bool(
                image_bytes and image_bytes.base64_counted
            ),
            max_image_px=min(px_values) if px_values else None,
            many_images_threshold=threshold,
            many_images_max_px=many_px,
            bytes_ceiling=bytes_ceiling,
            sources=tuple(resolved),
            model_aware=True,
        )

    @classmethod
    def ceiling_only(
        cls,
        *,
        page_ceiling: int | None = None,
        bytes_ceiling: int | None = None,
        legacy_cap: int | None = None,
    ) -> ImageModePolicy:
        """Policy for callers that do not know the LLM: ceilings only."""
        max_pages = ImageOutputConstants.LLMWHISPERER_MAX_PAGES
        binding = "llmwhisperer"
        for name, value in (("ceiling", page_ceiling), ("legacy", legacy_cap)):
            if value is not None and value < max_pages:
                max_pages, binding = value, name
        budget = PageBudget(
            max_pages=max_pages,
            binding=binding,
            limits=None,
            context_tokens=None,
            advisory_max_images=None,
            terms={
                "llmwhisperer": ImageOutputConstants.LLMWHISPERER_MAX_PAGES,
                "ceiling": page_ceiling,
                "legacy": legacy_cap,
            },
        )
        return cls(
            page_budget=budget,
            request_bytes=None,
            advisory_request_bytes=None,
            max_image_bytes=None,
            max_image_bytes_base64_counted=False,
            max_image_px=None,
            many_images_threshold=None,
            many_images_max_px=None,
            bytes_ceiling=bytes_ceiling,
            sources=(),
            model_aware=False,
        )

    def raw_byte_budget(
        self, *, page_count: int, prompt_text_bytes: int | None = None
    ) -> int | None:
        """Raw image bytes that fit under the request limit (and ceiling).

        A base64-counted limit is reduced by the text the request carries
        and by base64's 4/3 inflation; a raw-counted limit is used as is.
        ``None`` means no enforceable limit.
        """
        budgets: list[int] = []
        if self.request_bytes is not None and self.request_bytes.value is not None:
            limit = self.request_bytes.value
            if self.request_bytes.base64_counted:
                text = _text_bytes(page_count, prompt_text_bytes)
                budgets.append(max((limit - text) * _B64_DEN // _B64_NUM, 0))
            else:
                budgets.append(limit)
        if self.bytes_ceiling is not None:
            budgets.append(self.bytes_ceiling)
        return min(budgets) if budgets else None

    def advisories(self, *, page_count: int) -> list[str]:
        """Warnings to log for limits that are known but not enforced."""
        lines: list[str] = []
        budget = self.page_budget
        if budget.advisory_max_images is not None and budget.limits is not None:
            limits = budget.limits
            if page_count > budget.advisory_max_images:
                lines.append(
                    f"{_model_label(limits)} publishes no image limit; this document "
                    f"has {page_count} pages, above Unstract's conservative default "
                    f"of {budget.advisory_max_images} images. The request will be "
                    "sent; the server may reject it."
                )
        if self.advisory_request_bytes is not None and self.advisory_request_bytes.value:
            limits = next(
                (
                    lim
                    for lim in self.sources
                    if lim.max_request_bytes is self.advisory_request_bytes
                ),
                None,
            )
            label = _model_label(limits) if limits else "this model"
            lines.append(
                f"{label} publishes no request-size limit; Unstract's conservative "
                f"default is {_mb(self.advisory_request_bytes.value)} per "
                "request and is not enforced for this provider."
            )
        return lines

    def size_advisory(self, *, page_count: int) -> str | None:
        """Pre-conversion hint when the pages will probably exceed the byte limit.

        Page bytes are only known after the billed conversion; this uses the
        median page size, so it warns and never rejects.
        """
        budget = self.raw_byte_budget(page_count=page_count)
        if budget is None:
            return None
        estimate = page_count * ASSUMED_PAGE_BYTES
        if estimate <= budget:
            return None
        limits = self.page_budget.limits
        label = _model_label(limits) if limits else "the LLM"
        return (
            f"At a typical {ASSUMED_PAGE_BYTES // 1000} KB per page, {page_count} "
            f"pages (~{_mb(estimate)}) may exceed the request-size limit of "
            f"{label}. The conversion is billed before page sizes are known."
        )

    def ceiling_binds_bytes(self) -> bool:
        """True when the operator/legacy ceiling is below the model's byte limit.

        Compared on raw bytes, ignoring the prompt text, so it is the same
        answer for every page count that matters for a summary line.
        """
        if self.bytes_ceiling is None:
            return False
        if self.request_bytes is None or self.request_bytes.value is None:
            return True
        model_raw = _raw_equivalent(self.request_bytes)
        return model_raw is None or self.bytes_ceiling < model_raw

    def describe(self) -> str:
        """Summary line for run logs: the limits that will actually bind."""
        ceiling = (
            f"{_mib(self.bytes_ceiling)} of page images per request (platform limit)"
            if self.bytes_ceiling is not None and self.ceiling_binds_bytes()
            else None
        )
        if not self.model_aware:
            parts = [self.page_budget.describe()]
            if ceiling:
                parts.append(ceiling)
            return f"Image mode limits: {'; '.join(parts)} (LLM not known at this point)"
        limits = self.page_budget.limits
        parts = [self.page_budget.describe()]
        if ceiling:
            parts.append(ceiling)
        elif self.request_bytes and self.request_bytes.value and limits is not None:
            source = format_limit_source(
                self.request_bytes, limits, with_table_version=False
            )
            parts.append(f"{_mb(self.request_bytes.value)} per request ({source})")
        if limits is not None and limits.table_version:
            parts.append(f"limits table {limits.table_version}")
        return "Image mode limits: " + "; ".join(parts)


# --- Checks -------------------------------------------------------------------


def _text_bytes(page_count: int, prompt_text_bytes: int | None) -> int:
    prompt = TEXT_RESERVE_BYTES if prompt_text_bytes is None else prompt_text_bytes
    return prompt + page_count * PAGE_LABEL_OVERHEAD_BYTES


def estimate_wire_bytes(
    raw_bytes: int, *, page_count: int, prompt_text_bytes: int | None = None
) -> int:
    """Approximate request body size: base64 images plus the text parts."""
    return raw_bytes * _B64_NUM // _B64_DEN + _text_bytes(page_count, prompt_text_bytes)


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    """``(width, height)`` from a PNG's IHDR chunk, or None if not parseable."""
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        return None
    return width, height


def check_page_image(
    policy: ImageModePolicy,
    *,
    page_number: int,
    page_count: int,
    data: bytes,
    page_store_dir: str,
) -> None:
    """Apply the per-image byte and pixel limits to one page."""
    if not ENFORCE_PER_IMAGE_LIMITS:
        return
    if policy.max_image_bytes is not None and len(data) > policy.max_image_bytes:
        raise PageImageTooLargeError(
            page_too_large_message(
                policy,
                page_number=page_number,
                kind="bytes",
                actual=len(data),
                limit=policy.max_image_bytes,
                dims=None,
                many_images=False,
            ),
            page_store_dir=page_store_dir,
            page_number=page_number,
            limit_kind="bytes",
            actual=len(data),
            limit=policy.max_image_bytes,
        )
    px_limit = policy.max_image_px
    many = False
    if (
        policy.many_images_threshold is not None
        and policy.many_images_max_px is not None
        and page_count > policy.many_images_threshold
        and (px_limit is None or policy.many_images_max_px < px_limit)
    ):
        px_limit = policy.many_images_max_px
        many = True
    if px_limit is None:
        return
    dims = png_dimensions(data)
    if dims is None:
        return
    longest = max(dims)
    if longest > px_limit:
        raise PageImageTooLargeError(
            page_too_large_message(
                policy,
                page_number=page_number,
                kind="pixels",
                actual=longest,
                limit=px_limit,
                dims=dims,
                many_images=many,
            ),
            page_store_dir=page_store_dir,
            page_number=page_number,
            limit_kind="pixels",
            actual=longest,
            limit=px_limit,
        )


def check_page_set(
    policy: ImageModePolicy,
    pages: Sequence[tuple[int, bytes]],
    *,
    page_store_dir: str,
    prompt_text_bytes: int | None = None,
    charged: bool | None = None,
) -> None:
    """Check a whole page set in memory: count, per-image, then total bytes.

    ``charged`` says whether the conversion has already been billed so the
    message can be honest about it (None: say nothing).
    """
    page_count = len(pages)
    budget = policy.page_budget
    if page_count > budget.max_pages:
        raise PageCapExceededError(
            page_cap_message(page_count, budget, charged=charged),
            page_store_dir=page_store_dir,
            page_count=page_count,
            page_cap=budget.max_pages,
        )
    total = 0
    for page_number, data in pages:
        check_page_image(
            policy,
            page_number=page_number,
            page_count=page_count,
            data=data,
            page_store_dir=page_store_dir,
        )
        total += len(data)
    raw_budget = policy.raw_byte_budget(
        page_count=page_count, prompt_text_bytes=prompt_text_bytes
    )
    if raw_budget is not None and total > raw_budget:
        raise PageImageSetTooLargeError(
            request_too_large_message(
                policy,
                page_count=page_count,
                raw_total=total,
                prompt_text_bytes=prompt_text_bytes,
                charged=charged,
            ),
            page_store_dir=page_store_dir,
            total_bytes=total,
            max_total_bytes=raw_budget,
        )
    for line in policy.advisories(page_count=page_count):
        logger.warning("Image mode: %s", line)


# --- Messages -----------------------------------------------------------------


def _model_label(limits: ImageRequestLimits | None) -> str:
    if limits is None:
        return "the LLM"
    return f"`{limits.model}` on {limits.provider_label}"


def format_limit_source(
    limit: LimitValue, limits: ImageRequestLimits, *, with_table_version: bool = True
) -> str:
    """Provenance clause for a limit: documented, unverified, or a default.

    Ends with the limits-table version (date, bundled/remote, hash) so a
    reported error says which copy of the table produced the number.
    """
    checked = f", checked {limit.verified_on}" if limit.verified_on else ""
    if limit.from_default:
        clause = (
            f"no published limit is known for this model on {limits.provider_label}, "
            "so Unstract applies a conservative default"
        )
    elif limit.confidence == "verified":
        clause = f"documented by {limits.provider_label}{checked}"
    else:
        clause = (
            f"not confirmed by {limits.provider_label}'s documentation; "
            f"Unstract's best estimate{checked}"
        )
    if limit.layer == "override":
        clause += "; set by this installation's limits override file"
    if with_table_version and limits.table_version:
        clause += f"; limits table {limits.table_version}"
    return clause


_SPLIT_ADVICE = (
    "Split the document into smaller files, pick a profile whose LLM accepts "
    "more pages, or switch to a text output mode."
)


def _charged_clause(charged: bool | None, *, size_known_late: bool = False) -> str:
    if charged is None:
        return ""
    if charged:
        if size_known_late:
            return (
                " The page conversion has already been charged, because image "
                "sizes are only known after the pages are rendered."
            )
        return " The page conversion was already charged."
    return " No pages were converted or charged."


def page_cap_message(page_count: int, budget: PageBudget, *, charged: bool | None) -> str:
    """User-facing text for a document with more pages than the budget."""
    limits = budget.limits
    if budget.binding == "tokens" and limits is not None:
        per_page = limits.tokens_per_image.value or 0
        reason = (
            f"At about {per_page:,} tokens per page it would need about "
            f"{page_count * per_page:,} tokens, over the "
            f"{(budget.context_tokens or 0):,}-token "
            f"context window of {_model_label(limits)}; the most it can take is "
            f"{budget.max_pages} pages."
        )
    elif budget.binding == "images" and limits is not None:
        reason = (
            f"{_model_label(limits)} accepts up to {budget.max_pages} page images in "
            "one request "
            f"({format_limit_source(limits.max_images_per_request, limits)}), "
            "and image output mode sends every page together."
        )
    else:
        described = budget.describe()
        reason = (
            f"{described[0].upper()}{described[1:]}, and image output mode "
            "sends every page together."
        )
    return (
        f"This document has {page_count} pages. {reason} {_SPLIT_ADVICE}"
        f"{_charged_clause(charged)}"
    )


def request_too_large_message(
    policy: ImageModePolicy,
    *,
    page_count: int,
    raw_total: int,
    prompt_text_bytes: int | None,
    charged: bool | None,
) -> str:
    """User-facing text for a page set over the request-size limit."""
    wire = estimate_wire_bytes(
        raw_total, page_count=page_count, prompt_text_bytes=prompt_text_bytes
    )
    limit = policy.request_bytes
    if limit is not None and policy.bytes_ceiling is not None:
        model_budget = dataclasses.replace(policy, bytes_ceiling=None).raw_byte_budget(
            page_count=page_count, prompt_text_bytes=prompt_text_bytes
        )
        if model_budget is not None and policy.bytes_ceiling < model_budget:
            limit = None  # the ceiling bound, not the model's limit
    limits = next(
        (
            lim
            for lim in policy.sources
            if limit is not None and lim.max_request_bytes is limit
        ),
        None,
    )
    # The total and the limit are printed in the limit's own unit: decimal
    # MB for a provider limit, MiB for the (raw-byte) operator/legacy ceiling.
    if limit is not None and limit.value is not None and limits is not None:
        size = f"total {_mb(raw_total)} ({_mb(wire)} once encoded)"
        bound = (
            f"over the {_mb(limit.value)} request limit of "
            f"{_model_label(limits)} "
            f"({format_limit_source(limit, limits)})"
        )
    else:
        size = f"total {_mib(raw_total)}"
        bound = (
            f"over the {_mib(policy.bytes_ceiling or 0)} limit for one image-mode "
            "request"
        )
    return (
        f"The {page_count} page images of this document {size}, {bound}, and "
        "image output mode sends "
        f"every page in one request. Split the document into smaller files, or "
        f"switch to a text output mode.{_charged_clause(charged, size_known_late=True)}"
    )


def page_too_large_message(
    policy: ImageModePolicy,
    *,
    page_number: int,
    kind: str,
    actual: int,
    limit: int,
    dims: tuple[int, int] | None,
    many_images: bool,
) -> str:
    """User-facing text for a single page over a per-image limit."""
    limits = policy.page_budget.limits
    if kind == "bytes":
        measured = _mb(actual)
        bound = _mb(limit)
    else:
        measured = f"{dims[0]}×{dims[1]} px" if dims else f"{actual} px"
        bound = f"{limit} px per side"
    when = (
        f" when more than {policy.many_images_threshold} images are sent"
        if many_images and policy.many_images_threshold is not None
        else ""
    )
    return (
        f"Page {page_number} of this document is {measured}, over the per-image "
        f"limit of {bound} for {_model_label(limits)}{when}. Reduce the page's "
        "render resolution, or use a model with larger per-image limits; "
        "splitting the document does not help."
    )
