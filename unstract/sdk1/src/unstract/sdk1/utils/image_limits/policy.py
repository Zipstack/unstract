"""Turn resolved image limits into the checks image output mode enforces.

Two ceilings bound how many page images one request can carry: the
provider's image count and LLMWhisperer's 999-page conversion maximum,
plus optional operator ceilings. ``compute_page_budget`` picks the
binding one and remembers why, so every error message can say which
limit the user hit and where the number came from. The model's context
window, estimated from a per-page token figure, is WARN ONLY: a token
count per page is an estimate whichever table entry it comes from, so it
is reported to the user and never rejects a document.

Byte limits are only checkable once pages are rendered: ``ImageModePolicy``
converts a provider's wire limit (base64 JSON body) into a raw-byte budget
for the loader's bounded reads, and ``check_page_set`` applies the
per-image and whole-set checks to a page set in memory.

Pass-through providers (Ollama, OpenAI-compatible servers, NVIDIA Build,
unknown OpenRouter upstreams) publish no limits. Their count/byte values
come from the table's conservative default and are ADVISORY: the policy
reports what the default would have been instead of rejecting a document
the operator's server might well accept. Advisories go to the worker log
and, through ``ImageModePolicy.with_advisory_sink``, to the user's run log.

``VLM_IMAGE_LIMITS_ENFORCE=false`` turns the model-aware checks off at
runtime, inside this module: ``ImageModePolicy.from_limits``,
``compute_page_budget`` and ``extraction_bound_kwargs`` then yield the
fixed 90-page / 14 MiB cap (``ImageModePolicy.fixed_cap``) whatever limits
they are given, so every consumer honours the switch without checking it.

Tunables are module constants so a product decision is one edit.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import struct
import threading
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
    is_page_selection,
)
from unstract.sdk1.utils.image_limits.source import MAX_REMOTE_RAISE_FACTOR

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from unstract.sdk1.utils.image_limits.resolve import ImageRequestLimits, LimitValue

logger = logging.getLogger(__name__)

# --- Tunables (product decisions; one edit each) -------------------------
# Tokens kept back from the context window for the prompt, system text and
# the answer when deriving the token-based page estimate.
PROMPT_TOKENS_RESERVE = 4_000
# The context-window term is WARN ONLY (product decision, UN-4427). Its
# tokens-per-page figure is an estimate whether it is the table's default
# (1,500, which held 128K gpt-4o to 82 pages where ~90 fit) or a
# model-specific entry, so it is reported and never rejects a document; the
# provider's own context-length rejection remains the backstop. Image count
# and byte limits stay enforced.
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
# TEMPORARY rollout bound (UN-4427). While True, every image-mode policy
# (extraction here, answering in the cloud vlm-image-answer plugin, through
# extraction_bound_kwargs) is also held to the legacy limits: 90 pages /
# 14 MiB, or their env overrides, which REPLACE those values rather than cap
# them. Set to False — and delete with the legacy accessors — once the cloud
# plugin that answers with model-aware limits is released; the env vars then
# become ceilings on the model's limits.
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

# Runtime switch back to the fixed cap: "false" makes every builder below
# (``from_limits``, ``compute_page_budget``, ``extraction_bound_kwargs``)
# yield the fixed cap (``ImageModePolicy.fixed_cap``) instead of the LLM's
# limits, for extraction, upload and answering alike. For when a table
# value turns out wrong and an override file is not practical. Unset or
# "true" keeps model-aware limits.
ENFORCE_ENV = "VLM_IMAGE_LIMITS_ENFORCE"
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})


# Whether this process has logged that the switch is off: ``from_limits``
# runs per profile render, so the warning is once per process.
_switched_off_logged = False
_switched_off_lock = threading.Lock()


def _warn_switched_off_once() -> None:
    global _switched_off_logged
    with _switched_off_lock:
        if _switched_off_logged:
            return
        _switched_off_logged = True
    logger.warning(
        "Image mode: %s=false; applying the fixed page and byte cap instead of "
        "the LLM's limits (logged once per process)",
        ENFORCE_ENV,
    )


def model_aware_limits_enabled() -> bool:
    """False when ``VLM_IMAGE_LIMITS_ENFORCE`` turns model-aware limits off."""
    raw = os.environ.get(ENFORCE_ENV)
    if raw is None or not raw.strip():
        return True
    value = raw.strip().lower()
    if value in _FALSE_VALUES:
        return False
    if value not in _TRUE_VALUES:
        _report_invalid_switch_once(raw)
    return True


# Invalid values already reported by this process: the switch is read per
# lookup, so each distinct bad value is logged once.
_invalid_switch_logged: set[str] = set()


def _report_invalid_switch_once(raw: str) -> None:
    with _switched_off_lock:
        if raw in _invalid_switch_logged:
            return
        _invalid_switch_logged.add(raw)
    logger.error(
        "Invalid %s value %r (expected true or false); keeping model-aware "
        "image limits on (logged once per process)",
        ENFORCE_ENV,
        raw,
    )


def fixed_cap_bound_kwargs() -> dict[str, int | None]:
    """The fixed 90-page / 14 MiB cap (or its env overrides), for ``ceiling_only``.

    What image mode enforced before model-aware limits, and what it falls
    back to when ``VLM_IMAGE_LIMITS_ENFORCE=false``.
    """
    return {
        "page_ceiling": None,
        "bytes_ceiling": configured_max_total_bytes(),
        "legacy_cap": configured_page_cap(),
    }


def extraction_bound_kwargs() -> dict[str, int | None]:
    """Ceilings every image-mode policy applies on top of the model's limits.

    Operator ceilings (``VLM_IMAGE_ANSWER_PAGE_CAP`` /
    ``VLM_IMAGE_ANSWER_MAX_TOTAL_MB``) always apply; while
    ``LEGACY_ANSWER_BOUNDS_ACTIVE``, or when ``VLM_IMAGE_LIMITS_ENFORCE=false``,
    the fixed 90-page / 14 MiB limits are used instead, so extraction is
    never looser than the plugin. Pass the result to
    ``ImageModePolicy.from_limits`` / ``ceiling_only``.
    """
    if LEGACY_ANSWER_BOUNDS_ACTIVE or not model_aware_limits_enabled():
        # The legacy accessors already fold the same env vars in.
        return fixed_cap_bound_kwargs()
    return {
        "page_ceiling": configured_page_ceiling(),
        "bytes_ceiling": configured_request_bytes_ceiling(),
        "legacy_cap": None,
    }


def _stricter(value: int | None, fixed: int | None) -> int | None:
    """The smaller of two optional bounds (None means no bound)."""
    if value is None:
        return fixed
    if fixed is None:
        return value
    return min(value, fixed)


# --- Page budget -----------------------------------------------------------


@dataclass(frozen=True)
class PageBudget:
    """The effective page cap and the term that produced it."""

    max_pages: int
    binding: str  # images | llmwhisperer | ceiling | legacy
    limits: ImageRequestLimits | None
    context_tokens: int | None
    advisory_max_images: int | None
    terms: Mapping[str, int | None] = field(default_factory=dict)
    # Pages that fit the context window at the tokens-per-page estimate:
    # warned about, never enforced (the token term is warn only).
    advisory_token_pages: int | None = None

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
    """The smallest of the image-count, LLMWhisperer and ceiling terms.

    ``context_tokens`` is the caller's context-window figure (adapter,
    litellm registry); a ``max_input_tokens`` value in the table overrides
    it. The token term (context window / tokens per page) is computed for
    the advisory only and never lowers ``max_pages``. An unknown context
    skips it rather than inventing a number. An advisory image count
    (pass-through provider on the default) is recorded but not applied.

    With ``VLM_IMAGE_LIMITS_ENFORCE=false`` it returns the fixed cap's
    budget instead (``ImageModePolicy.fixed_cap``), ignoring ``limits``.
    """
    if not model_aware_limits_enabled():
        return ImageModePolicy.fixed_cap(
            page_ceiling=page_ceiling, legacy_cap=legacy_cap
        ).page_budget
    reserve = (
        PROMPT_TOKENS_RESERVE if prompt_tokens_reserve is None else prompt_tokens_reserve
    )
    terms: dict[str, int | None] = {}

    count = limits.max_images_per_request
    advisory_count = count.value if count.advisory else None
    terms["images"] = None if count.advisory else count.value

    context = limits.max_input_tokens.value or context_tokens
    per_page = limits.tokens_per_image.value
    advisory_tokens: int | None = None
    if context and per_page:
        advisory_tokens = max((context - reserve) // per_page, 0)
    terms["tokens"] = None  # warn only, never enforced
    terms["llmwhisperer"] = ImageOutputConstants.LLMWHISPERER_MAX_PAGES
    terms["ceiling"] = page_ceiling
    terms["legacy"] = legacy_cap

    binding = "llmwhisperer"
    max_pages = ImageOutputConstants.LLMWHISPERER_MAX_PAGES
    # Order decides ties: a model limit equal to the ceiling is still the
    # model's limit, which is the more useful thing to tell the user.
    for name in ("images", "llmwhisperer", "ceiling", "legacy"):
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
        advisory_token_pages=advisory_tokens,
    )


# --- Policy ----------------------------------------------------------------


def _raw_equivalent(limit: LimitValue) -> int | None:
    if limit.value is None:
        return None
    return limit.value * _B64_DEN // _B64_NUM if limit.base64_counted else limit.value


def _min_limit(
    pairs: Iterable[tuple[LimitValue, ImageRequestLimits]],
) -> tuple[LimitValue, ImageRequestLimits] | None:
    """The strictest enforced limit (raw-byte equivalent) and the LLM it is from."""
    best: tuple[LimitValue, ImageRequestLimits] | None = None
    for value, source in pairs:
        if value.value is None or value.advisory:
            continue
        if best is None or (_raw_equivalent(value) or 0) < (
            _raw_equivalent(best[0]) or 0
        ):
            best = (value, source)
    return best


@dataclass(frozen=True)
class ManyImagesRule:
    """Above ``threshold`` images, each image must be <= ``max_px`` per side."""

    threshold: int
    max_px: int
    source: ImageRequestLimits


@dataclass(frozen=True)
class ImageModePolicy:
    """Everything the extraction and answer paths need to check a page set.

    Each per-image limit keeps the LLM it came from (``*_source``), so a
    message about it names that model, not the one that set the page budget.
    """

    page_budget: PageBudget
    request_bytes: LimitValue | None  # enforced wire/raw limit, if any
    advisory_request_bytes: LimitValue | None
    max_image_bytes: int | None
    max_image_bytes_base64_counted: bool
    max_image_px: int | None
    many_images_rules: tuple[ManyImagesRule, ...]
    bytes_ceiling: int | None  # operator ceiling on raw bytes
    sources: tuple[ImageRequestLimits, ...]
    model_aware: bool
    # True when ``VLM_IMAGE_LIMITS_ENFORCE=false`` replaced the LLM's limits.
    switched_off: bool = False
    max_image_bytes_source: ImageRequestLimits | None = None
    max_image_px_source: ImageRequestLimits | None = None
    # Every LLM's own budget (``page_budget`` is the smallest), for advisories.
    page_budgets: tuple[PageBudget, ...] = ()
    # Where advisories go besides the worker log (e.g. the user's run log).
    advisory_sink: Callable[[str], None] | None = field(
        default=None, compare=False, repr=False
    )

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
        """Build the policy for one or more LLMs (the strictest of each wins).

        With ``VLM_IMAGE_LIMITS_ENFORCE=false`` the LLMs' limits are ignored
        and the fixed cap is returned (``fixed_cap``), still tightened by
        any stricter bound passed here.
        """
        if not resolved:
            raise ValueError("from_limits needs at least one resolved limit set")
        if not model_aware_limits_enabled():
            _warn_switched_off_once()
            return cls.fixed_cap(
                page_ceiling=page_ceiling,
                bytes_ceiling=bytes_ceiling,
                legacy_cap=legacy_cap,
            )
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

        request = _min_limit((lim.max_request_bytes, lim) for lim in resolved)
        advisory_bytes = next(
            (lim.max_request_bytes for lim in resolved if lim.max_request_bytes.advisory),
            None,
        )
        image_bytes = _min_limit((lim.max_image_bytes, lim) for lim in resolved)
        px = min(
            ((lim.max_image_px.value, lim) for lim in resolved if lim.max_image_px.value),
            key=lambda pair: pair[0],
            default=None,
        )
        # Kept per model: minimising the threshold and the pixel bound
        # separately could build a pair no model has.
        rules = tuple(
            ManyImagesRule(
                threshold=lim.many_images_threshold.value,
                max_px=lim.many_images_max_px.value,
                source=lim,
            )
            for lim in resolved
            if lim.many_images_threshold.value and lim.many_images_max_px.value
        )
        return cls(
            page_budget=page_budget,
            request_bytes=request[0] if request else None,
            advisory_request_bytes=advisory_bytes,
            max_image_bytes=_raw_equivalent(image_bytes[0]) if image_bytes else None,
            max_image_bytes_base64_counted=bool(
                image_bytes and image_bytes[0].base64_counted
            ),
            max_image_px=px[0] if px else None,
            many_images_rules=rules,
            bytes_ceiling=bytes_ceiling,
            sources=tuple(resolved),
            model_aware=True,
            max_image_bytes_source=image_bytes[1] if image_bytes else None,
            max_image_px_source=px[1] if px else None,
            page_budgets=tuple(budgets),
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
            many_images_rules=(),
            bytes_ceiling=bytes_ceiling,
            sources=(),
            model_aware=False,
        )

    @classmethod
    def fixed_cap(
        cls,
        *,
        page_ceiling: int | None = None,
        bytes_ceiling: int | None = None,
        legacy_cap: int | None = None,
    ) -> ImageModePolicy:
        """The fixed 90-page / 14 MiB policy ``VLM_IMAGE_LIMITS_ENFORCE=false`` uses.

        ``fixed_cap_bound_kwargs`` (90 pages / 14 MiB or their env
        overrides), tightened by any stricter bound given; never looser.
        """
        fixed = fixed_cap_bound_kwargs()
        policy = cls.ceiling_only(
            page_ceiling=page_ceiling,
            bytes_ceiling=_stricter(bytes_ceiling, fixed["bytes_ceiling"]),
            legacy_cap=_stricter(legacy_cap, fixed["legacy_cap"]),
        )
        return dataclasses.replace(policy, switched_off=True)

    def with_advisory_sink(self, sink: Callable[[str], None] | None) -> ImageModePolicy:
        """This policy, also sending advisories to ``sink`` (e.g. a run log)."""
        return dataclasses.replace(self, advisory_sink=sink)

    def warn(self, line: str) -> None:
        """Log an advisory and pass it to the sink; a failing sink is logged."""
        logger.warning("Image mode: %s", line)
        if self.advisory_sink is None:
            return
        try:
            self.advisory_sink(line)
        except Exception:
            logger.warning("Could not stream an image-mode advisory", exc_info=True)

    def emit_advisories(self, *, page_count: int, include_size: bool = False) -> None:
        """``warn`` each advisory for ``page_count`` (and the size hint)."""
        for line in self.advisories(page_count=page_count):
            self.warn(line)
        if include_size:
            hint = self.size_advisory(page_count=page_count)
            if hint:
                self.warn(hint)

    def request_bytes_source(self) -> ImageRequestLimits | None:
        """The LLM whose request-size limit is enforced, if any."""
        if self.request_bytes is None:
            return None
        return next(
            (lim for lim in self.sources if lim.max_request_bytes is self.request_bytes),
            None,
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
        # Every LLM's own budget: with several LLMs the advisory one is often
        # not the one whose enforced limit set ``page_budget``.
        budgets = self.page_budgets or (self.page_budget,)
        for each in budgets:
            advisory, limits = each.advisory_max_images, each.limits
            if advisory is not None and limits is not None and page_count > advisory:
                lines.append(
                    f"{_model_label(limits)} publishes no image limit; this document "
                    f"has {page_count} pages, above Unstract's conservative default "
                    f"of {advisory} images. The request will be sent; the server "
                    "may reject it."
                )
        for each in budgets:
            line = _token_advisory(each, page_count=page_count)
            if line:
                lines.append(line)
        for limits in self.sources:
            request = limits.max_request_bytes
            if request.advisory and request.value:
                lines.append(
                    f"{_model_label(limits)} publishes no request-size limit; "
                    f"Unstract's conservative default is {_mb(request.value)} per "
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
        limits = self.request_bytes_source() or self.page_budget.limits
        label = _model_label(limits) if limits else "the LLM"
        if self.bytes_ceiling is not None and self.ceiling_binds_bytes():
            label = "one image-mode request (platform limit)"
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
            why = (
                f"the LLM's own limits are turned off by {ENFORCE_ENV}=false"
                if self.switched_off
                else "LLM not known at this point"
            )
            return f"Image mode limits: {'; '.join(parts)} ({why})"
        limits = self.page_budget.limits
        parts = [self.page_budget.describe()]
        request_source = self.request_bytes_source()
        if ceiling:
            parts.append(ceiling)
        elif self.request_bytes and self.request_bytes.value and request_source:
            source = format_limit_source(
                self.request_bytes, request_source, with_table_version=False
            )
            parts.append(
                f"{_mb(self.request_bytes.value)} per request for "
                f"{_model_label(request_source)} ({source})"
            )
        if self.max_image_bytes is not None and self.max_image_bytes_source:
            parts.append(
                f"{_mb(self.max_image_bytes)} per page image for "
                f"{_model_label(self.max_image_bytes_source)}"
            )
        if self.max_image_px is not None and self.max_image_px_source:
            parts.append(
                f"{self.max_image_px} px per side for "
                f"{_model_label(self.max_image_px_source)}"
            )
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
    document_page: int | None = None,
) -> None:
    """Apply the per-image byte and pixel limits to one page.

    ``page_number`` is the image position (kept on the error);
    ``document_page``, when known, is the page the message names.
    """
    if not ENFORCE_PER_IMAGE_LIMITS:
        return
    if policy.max_image_bytes is not None and len(data) > policy.max_image_bytes:
        raise PageImageTooLargeError(
            page_too_large_message(
                policy,
                page_number=document_page or page_number,
                kind="bytes",
                actual=len(data),
                limit=policy.max_image_bytes,
                dims=None,
                source=policy.max_image_bytes_source,
                threshold=None,
            ),
            page_store_dir=page_store_dir,
            page_number=page_number,
            limit_kind="bytes",
            actual=len(data),
            limit=policy.max_image_bytes,
        )
    px_limit = policy.max_image_px
    px_source = policy.max_image_px_source
    threshold: int | None = None
    for rule in policy.many_images_rules:
        if page_count > rule.threshold and (px_limit is None or rule.max_px < px_limit):
            px_limit, px_source, threshold = rule.max_px, rule.source, rule.threshold
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
                page_number=document_page or page_number,
                kind="pixels",
                actual=longest,
                limit=px_limit,
                dims=dims,
                source=px_source,
                threshold=threshold,
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
    emit_advisories: bool = True,
    document_pages: Sequence[int] | None = None,
) -> None:
    """Check a whole page set in memory: count, per-image, then total bytes.

    ``document_pages`` (one per image, from a 'Pages to extract' selection)
    makes per-image errors name the document page instead of the position.

    ``charged`` says whether the conversion has already been billed so the
    message can be honest about it (None: say nothing). ``emit_advisories``
    False skips the advisories when the caller already reported them for
    this page count.
    """
    page_count = len(pages)
    budget = policy.page_budget
    if page_count > budget.max_pages:
        raise PageCapExceededError(
            page_cap_message(
                page_count,
                budget,
                charged=charged,
                selected=is_page_selection(document_pages),
            ),
            page_store_dir=page_store_dir,
            page_count=page_count,
            page_cap=budget.max_pages,
        )
    total = 0
    for index, (page_number, data) in enumerate(pages):
        check_page_image(
            policy,
            page_number=page_number,
            page_count=page_count,
            data=data,
            page_store_dir=page_store_dir,
            document_page=document_pages[index] if document_pages else None,
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
    if emit_advisories:
        policy.emit_advisories(page_count=page_count)


# --- Messages -----------------------------------------------------------------


def _token_advisory(budget: PageBudget, *, page_count: int) -> str | None:
    """Warn when ``page_count`` pages may not fit the budget's context window."""
    limits, fits = budget.limits, budget.advisory_token_pages
    if limits is None or fits is None or page_count <= fits:
        return None
    per_page = limits.tokens_per_image.value or 0
    estimate = (
        "Unstract's unverified default estimate"
        if limits.tokens_per_image.from_default
        else "the limits table's estimate for this model"
    )
    return (
        f"At {estimate} of {per_page:,} tokens per page, {page_count} pages "
        f"may exceed the {(budget.context_tokens or 0):,}-token context window "
        f"of {_model_label(limits)} (about {fits} pages fit). The request will "
        "be sent; the provider may reject it."
    )


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
    if limit.clamped:
        asked = (
            f"to {limit.clamped_from}"
            if limit.clamped_from is not None
            else "to no enforced limit"
        )
        clause += (
            f"; capped at {MAX_REMOTE_RAISE_FACTOR}x the value bundled with "
            f"this sdk1 (the remote limits table raised it {asked})"
        )
    if with_table_version and limits.table_version:
        clause += f"; limits table {limits.table_version}"
    return clause


_SPLIT_ADVICE = (
    "Split the document into smaller files, set the adapter's 'Pages to "
    "extract' to a smaller range, pick a profile whose LLM accepts more "
    "pages, or switch to a text output mode."
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


def _selection_clause(page_count: int, selected_from: int | None) -> str:
    """'Pages to extract' selects N [of this document's M] pages (no period)."""
    if selected_from is None:
        return f"'Pages to extract' selects {page_count} pages"
    return (
        f"'Pages to extract' selects {page_count} of this document's "
        f"{selected_from} pages"
    )


def page_cap_message(
    page_count: int,
    budget: PageBudget,
    *,
    charged: bool | None,
    selected_from: int | None = None,
    selected: bool = False,
) -> str:
    """User-facing text for a document with more pages than the budget.

    ``selected_from`` is the document's page count when 'Pages to extract'
    narrowed it to ``page_count``; the message then names the selection.
    ``selected`` names it without the document's count (unknown at answer
    time, when only the selected pages' images exist).
    """
    limits = budget.limits
    if budget.binding == "images" and limits is not None:
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
    opening = (
        f"{_selection_clause(page_count, selected_from)}."
        if selected_from is not None or selected
        else f"This document has {page_count} pages."
    )
    return f"{opening} {reason} {_SPLIT_ADVICE}{_charged_clause(charged)}"


def fixed_cap_message(
    page_count: int,
    page_cap: int,
    *,
    switch_to: str = "use a text output mode instead",
    charged: bool | None = None,
    selected_from: int | None = None,
    selected: bool = False,
) -> str:
    """User-facing text for a document over the FIXED page cap.

    The fixed cap applies when model-aware limits are off
    (``VLM_IMAGE_LIMITS_ENFORCE=false``) or no LLM is known;
    ``page_cap_message`` covers the model-aware budget. ``switch_to`` ends the
    advice ("switch this profile to a text output mode", ...).
    ``selected_from`` and ``selected`` name the selection as in
    ``page_cap_message``.
    """
    if selected_from is not None or selected:
        opening = (
            "Too many pages are selected for image output mode. "
            f"{_selection_clause(page_count, selected_from)}, and the limit is "
        )
    else:
        opening = (
            "This document has too many pages for image output mode. It has "
            f"{page_count} pages, and the limit is "
        )
    return (
        opening + f"{page_cap} because every page is "
        "sent to the LLM in one request. Split the document into smaller files, "
        "set the adapter's 'Pages to extract' to a smaller range, "
        f"or {switch_to}." + _charged_clause(charged)
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
    limits = policy.request_bytes_source() if limit is not None else None
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
    source: ImageRequestLimits | None,
    threshold: int | None,
) -> str:
    """User-facing text for a single page over a per-image limit.

    ``page_number`` is the page as the user knows it: the document page when
    a selection recorded it, else the image position.

    ``source`` is the LLM the broken limit belongs to (with several LLMs it
    can differ from the one that set the page budget); ``threshold`` is set
    when the many-images pixel rule applied.
    """
    limits = source or policy.page_budget.limits
    if kind == "bytes":
        measured = _mb(actual)
        bound = _mb(limit)
    else:
        measured = f"{dims[0]}×{dims[1]} px" if dims else f"{actual} px"
        bound = f"{limit} px per side"
    label = _model_label(limits)
    if threshold is not None:
        # The many-images rule: the page fits when at most ``threshold``
        # images go in one request, so splitting the document is a fix.
        return (
            f"Page {page_number} of this document is {measured}, over the "
            f"per-image limit of {bound} for {label} when more than {threshold} "
            f"images are sent. Send at most {threshold} pages per request: split "
            f"the document into files of at most {threshold} pages, reduce the "
            "page's render resolution, or use a model with larger per-image "
            "limits."
        )
    return (
        f"Page {page_number} of this document is {measured}, over the per-image "
        f"limit of {bound} for {label}. Reduce the page's render resolution, or "
        "use a model with larger per-image limits; splitting the document does "
        "not help."
    )
