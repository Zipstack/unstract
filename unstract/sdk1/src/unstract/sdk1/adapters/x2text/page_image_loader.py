"""FileStorage-backed reader for persisted page images.

Reader half of the page-image storage contract defined in
``unstract.sdk1.adapters.x2text.constants``: the LLMWhisperer adapter
(writer) persists one PNG per page as ``page_NNN.png`` under the directory
returned by ``build_page_store_dir``; this module discovers those pages via
the shared naming constants, orders them by their **integer** page index
(never lexicographically — that misorders past the zero-padding width),
base64-encodes them, and shapes multimodal content blocks for
``LLM.complete_vision``.

All reads go through the FileStorage abstraction so the same code serves
local disk and remote object storage. Discovery lists the
deterministic path — no manifest, no metadata transport.

Failure modes are typed so callers can surface distinct, actionable errors:

- ``PageImagesNotFoundError`` — directory missing/empty (never extracted in
  image mode, or fully purged).
- ``PageImageSetIncompleteError`` — pages exist but the 1..N set is broken
  (post-write loss). Distinct from "not found" so remediation can differ.
- ``PageCapExceededError`` — document larger than the page cap; callers
  must fail explicitly rather than silently truncate.
- ``PageImageSetTooLargeError`` / ``PageImageTooLargeError`` — the page set,
  or one page, breaks the request-size or per-image limits of the LLM.

Concurrency contract (designed, accepted): the writer resets and rewrites
the stable pages directory on re-extraction, so a read that overlaps a
same-document re-extraction may observe a missing or incomplete set. That
surfaces as the typed errors above — a loud, retryable failure — by
deliberate choice: silently mixing old and new pages into one answer is
the worse outcome, and atomic directory replacement does not exist on
object storage. See ``LLMWhispererHelper.persist_page_images`` for the
full rationale.
"""

import base64
import json
import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from unstract.sdk1.adapters.x2text.constants import ImageOutputConstants
from unstract.sdk1.file_storage import FileStorage

if TYPE_CHECKING:
    from unstract.sdk1.utils.image_limits.policy import ImageModePolicy

logger = logging.getLogger(__name__)

# The FIXED image-mode page cap: the whole limit when model-aware limits are
# off (``VLM_IMAGE_LIMITS_ENFORCE=false``), a caller knows no LLM (no
# ``ImageModePolicy``), or the LLM is a pass-through provider that publishes
# no limits. The operator ceiling can lower it, never raise it
# (``get_fixed_page_cap``). Model-aware limits come from
# ``unstract.sdk1.utils.image_limits``. Above the cap a
# document is rejected rather than windowed, because this path answers in a
# single call.
#
# Keep the value HERE: the cap is coupled to the byte budget below, and
# TestCapMatchesBudget can only check the pair when both live in this file.
# PAGE_CAP_ENV (an operator ceiling, see get_configured_page_ceiling) only ever
# lowers it.
#
# RAISING THIS ABOVE 999 ALSO NEEDS LLMWHISPERER CHANGES. Image mode's pages
# come from LLMWhisperer's /pdf-to-images endpoint, which:
#   - hardcodes a 999-page maximum (PDFToImagesConverter.MAX_PAGES, tied to
#     the page_001..page_999 file naming) with no env override — a cap above
#     999 here still fails there, with LLMWhisperer's less specific error.
#     Increases up to 999 need no service change;
#   - bills per converted page, so a document the cap admits but the byte
#     budget then rejects is still charged for every page.
# Coordinate anything above 999 with the LLMWhisperer service. For ANY
# increase, raise the byte budget and this cap together (or add windowing) —
# never the cap alone.
#
# 90 is derived from DEFAULT_MAX_TOTAL_BYTES below, not chosen independently:
# at the ~165-379KB per page measured from LLMWhisperer's 150 DPI renders, a
# 14MB budget holds roughly 38-89 pages (90 is the round number at the top
# of that range; the page sizes are approximate, measured from archive
# sizes on two test documents — see TestCapMatchesBudget).
# A higher cap is effectively unreachable — and worse, it defeats the
# extraction-time pre-check, which only knows the page COUNT: a 200-page
# document would pass a 300 cap, be converted and billed per page, then
# fail at answer time on the byte budget. Keeping the cap at the top of
# what the budget allows means a document over the cap is refused before
# any conversion is billed.
#
# NOTE: 90 is NOT under every provider's image-count limit — Azure OpenAI
# (50), Bedrock Converse (20), Mistral (8) and Nova 2 (5) are stricter, and
# OpenAI (1,500) / Gemini (3,600) are far looser. These fixed values apply
# only without a model-aware ``ImageModePolicy``; the model-aware limits live
# in ``unstract.sdk1.utils.image_limits``.
DEFAULT_PAGE_CAP = 90

# Aggregate raw-byte budget across all loaded pages. The page cap bounds the
# COUNT of images, not their size — without a byte budget, unusually large
# renders would grow worker memory and the provider request unbounded.
#
# Sized from the SMALLEST request limit across the providers this path can
# target (Amazon Bedrock and Gemini inline both cap a request at 20MB;
# Anthropic direct allows 32MB, Google Cloud 30MB), minus base64's ~33%
# inflation: 20MB / 1.34 ≈ 14MB of raw image bytes. A larger budget would
# let the provider reject the request before this check ever fires, which
# costs the caller a full read + encode and surfaces a raw provider error
# instead of the actionable one below.
#
# Like DEFAULT_PAGE_CAP above, keep the value HERE rather than in a Helm
# chart: the two are a coupled pair, checked together by
# TestCapMatchesBudget. VLM_IMAGE_ANSWER_MAX_TOTAL_MB is an operator
# ceiling (see get_configured_request_bytes_ceiling) that only ever lowers it.
DEFAULT_MAX_TOTAL_BYTES = 14 * 1024 * 1024

_PAGE_NAME_RE = re.compile(ImageOutputConstants.PAGE_NUMBER_REGEX)

# Operator settings for the two limits, defined next to the defaults so
# every site reads them the same way: the extraction-time checks (before
# and right after the per-page-billed conversion) and the answer-time
# enforcement (cloud consumer plugin). They are ceilings applied with min():
# on top of the LLM's limits (get_configured_page_ceiling /
# get_configured_request_bytes_ceiling) and on top of the fixed cap
# (get_fixed_page_cap / get_fixed_max_total_bytes). See DEFAULT_PAGE_CAP for why the
# defaults live in this file.
PAGE_CAP_ENV = "VLM_IMAGE_ANSWER_PAGE_CAP"
MAX_TOTAL_MB_ENV = "VLM_IMAGE_ANSWER_MAX_TOTAL_MB"


# (env name, raw value) pairs already reported as unusable: these are read
# on every page set and profile render, so each bad value is logged once.
_reported_bad_env: set[tuple[str, str]] = set()


def _env_value(name: str) -> str | None:
    """The variable's value, or None when unset or empty (empty means unset)."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    return raw


def _parse_positive(raw: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _first_report(name: str, raw: str) -> bool:
    key = (name, raw)
    if key in _reported_bad_env:
        return False
    _reported_bad_env.add(key)
    return True


def _optional_positive_int_env(name: str, default: int, *, scale: int = 1) -> int | None:
    """An optional ceiling: None when unset or empty, ``default`` when unusable.

    An invalid value must not remove the ceiling (unbounded reads into
    worker memory), so it is logged at ERROR (once per value) and the fixed
    default is kept. ``default`` is already in the scaled unit.
    """
    raw = _env_value(name)
    if raw is None:
        return None
    value = _parse_positive(raw)
    if value is None:
        if _first_report(name, raw):
            logger.error(
                "Invalid %s value %r (expected a positive integer); using the "
                "default %d instead",
                name,
                raw,
                default,
            )
        return default
    return value * scale


def get_configured_page_ceiling() -> int | None:
    """``PAGE_CAP_ENV`` read as an optional operator CEILING on the page budget.

    Model-aware policies apply it with ``min()`` on top of the model's own
    limits; unset means no ceiling beyond LLMWhisperer's 999. An invalid
    value keeps ``DEFAULT_PAGE_CAP``.
    """
    return _optional_positive_int_env(PAGE_CAP_ENV, DEFAULT_PAGE_CAP)


def get_configured_request_bytes_ceiling() -> int | None:
    """``MAX_TOTAL_MB_ENV`` (MiB, as before) as an optional raw-byte ceiling.

    An invalid value keeps ``DEFAULT_MAX_TOTAL_BYTES``.
    """
    return _optional_positive_int_env(
        MAX_TOTAL_MB_ENV, DEFAULT_MAX_TOTAL_BYTES, scale=1024 * 1024
    )


def get_fixed_page_cap() -> int:
    """The fixed page cap, lowered by ``PAGE_CAP_ENV`` but never raised.

    What image mode enforces without the LLM's limits: with
    ``VLM_IMAGE_LIMITS_ENFORCE=false``, when the caller knows no LLM, or for
    a pass-through provider that publishes no limits.
    """
    return min(DEFAULT_PAGE_CAP, get_configured_page_ceiling() or DEFAULT_PAGE_CAP)


def get_fixed_max_total_bytes() -> int:
    """The fixed raw-byte budget, lowered by ``MAX_TOTAL_MB_ENV`` (MiB), never raised."""
    return min(
        DEFAULT_MAX_TOTAL_BYTES,
        get_configured_request_bytes_ceiling() or DEFAULT_MAX_TOTAL_BYTES,
    )


def configured_page_cap() -> int:
    """Deprecated alias of ``get_fixed_page_cap``.

    Unlike the old accessor, an env value can no longer raise the cap.
    Kept for the released cloud answer plugin, which imports it; remove after
    Zipstack/unstract-cloud#1869 is deployed.
    """
    return get_fixed_page_cap()


def configured_max_total_bytes() -> int:
    """Deprecated alias of ``get_fixed_max_total_bytes``.

    Unlike the old accessor, an env value can no longer raise the budget.
    Kept for the released cloud answer plugin; remove after
    Zipstack/unstract-cloud#1869 is deployed.
    """
    return get_fixed_max_total_bytes()


class _UseConfigured:
    """Sentinel type: read the limit from the environment at call time."""


USE_CONFIGURED = _UseConfigured()


class PageImageLoadError(Exception):
    """Base error for page-image discovery/loading failures."""

    def __init__(self, message: str, *, page_store_dir: str) -> None:
        """Store the offending pages directory alongside the message."""
        super().__init__(message)
        self.page_store_dir = page_store_dir


class PageImagesNotFoundError(PageImageLoadError):
    """The pages directory is missing or contains no page images.

    Either the document was never extracted in image output mode, or the
    persisted images were purged. Remediation: re-extract the document with
    cache bypass (note: re-extraction re-submits to LLMWhisperer and is
    billed per page — a plain re-run is an extraction cache hit and will
    NOT regenerate images).
    """


class PageImageSetIncompleteError(PageImageLoadError):
    """Pages exist but the contiguous 1..N set is broken (post-write loss)."""

    def __init__(
        self,
        message: str,
        *,
        page_store_dir: str,
        found_pages: list[int],
        missing_pages: list[int],
    ) -> None:
        """Record which pages were found vs missing for remediation UIs."""
        super().__init__(message, page_store_dir=page_store_dir)
        self.found_pages = found_pages
        self.missing_pages = missing_pages


class PageCapExceededError(PageImageLoadError):
    """The document has more pages than the configured cap allows."""

    def __init__(
        self, message: str, *, page_store_dir: str, page_count: int, page_cap: int
    ) -> None:
        """Record the observed page count and the cap that was exceeded."""
        super().__init__(message, page_store_dir=page_store_dir)
        self.page_count = page_count
        self.page_cap = page_cap


class PageImageSetTooLargeError(PageImageLoadError):
    """The combined size of the page images exceeds the byte budget."""

    def __init__(
        self,
        message: str,
        *,
        page_store_dir: str,
        total_bytes: int,
        max_total_bytes: int,
    ) -> None:
        """Record the observed total and the budget that was exceeded."""
        super().__init__(message, page_store_dir=page_store_dir)
        self.total_bytes = total_bytes
        self.max_total_bytes = max_total_bytes


class PageImageTooLargeError(PageImageLoadError):
    """One page image breaks a per-image byte or pixel limit.

    Distinct from ``PageImageSetTooLargeError``: the page itself is over a
    limit. The message (``policy.page_too_large_message``) says what fixes it.
    """

    def __init__(
        self,
        message: str,
        *,
        page_store_dir: str,
        page_number: int,
        limit_kind: str,
        actual: int,
        limit: int,
    ) -> None:
        """Record the offending page and which per-image limit it broke."""
        super().__init__(message, page_store_dir=page_store_dir)
        self.page_number = page_number
        self.limit_kind = limit_kind  # "bytes" | "pixels"
        self.actual = actual
        self.limit = limit


@dataclass(frozen=True)
class LoadedPageImage:
    """A page image read from FileStorage, base64-encoded for a VLM call.

    ``page_number`` is the image's position (``page_NNN``, always 1..N).
    ``document_page`` is its page number in the source document when
    ``pages.json`` records it (a 'Pages to extract' selection), else None.
    """

    page_number: int
    path: str
    base64_data: str
    document_page: int | None = None

    @property
    def label_page(self) -> int:
        """The page number shown to the LLM: the document's, else the position."""
        return self.document_page or self.page_number


# Written next to the page images when a selection makes the document page
# numbers differ from the image positions: {"pages": [10, 12, ...]}, one
# entry per image in order. Used for the "Page N" labels and for naming
# document pages in limit errors.
PAGE_LABELS_FILENAME = "pages.json"
# Up to 999 six-digit page numbers fit comfortably; bounds a corrupt object.
_PAGE_LABELS_MAX_BYTES = 64 * 1024


def validate_document_pages(value: object, image_count: int) -> list[int] | None:
    """``value`` as document page numbers for ``image_count`` images, or None.

    Valid means a list of positive integers (not bools), strictly ascending
    (LLMWhisperer renders a selection in ascending order without
    duplicates), with exactly one entry per image.
    """
    if not isinstance(value, list) or len(value) != image_count or not value:
        return None
    if any(isinstance(p, bool) or not isinstance(p, int) or p < 1 for p in value):
        return None
    if any(a >= b for a, b in zip(value, value[1:], strict=False)):
        return None
    return list(value)


def is_page_selection(document_pages: Sequence[int] | None) -> bool:
    """Whether ``document_pages`` came from a selection (not simply 1..N)."""
    return document_pages is not None and list(document_pages) != list(
        range(1, len(document_pages) + 1)
    )


def _page_position(
    index: int, page_number: int, image_count: int, document_pages: list[int] | None
) -> str:
    """'page 12 (image 2 of 5)' with labels, else 'page 2 of 5'."""
    if document_pages:
        return f"page {document_pages[index]} (image {page_number} of {image_count})"
    return f"page {page_number} of {image_count}"


def read_document_pages(
    fs: FileStorage, page_store_dir: str, image_count: int
) -> list[int] | None:
    """Document page numbers recorded in ``pages.json``, or None.

    Call it only when the directory listing showed the file (see
    ``load_page_images``): a read of a missing file costs failed GETs and an
    fsspec cache flush. Fails open: a missing (removed since the listing),
    unreadable or invalid file means the labels fall back to the image
    positions; it never fails the prompt. An existing file that cannot be
    used is logged at ERROR: the extraction wrote it for a selection, so the
    labels shown are wrong.
    """
    path = str(PurePosixPath(page_store_dir) / PAGE_LABELS_FILENAME)
    try:
        raw = fs.read(path=path, mode="rb", length=_PAGE_LABELS_MAX_BYTES + 1)
    except FileNotFoundError:
        return None  # removed between the listing and this read
    except Exception as e:
        logger.error(
            "Image mode: could not read page labels %s (%s); labelling by position",
            path,
            e,
        )
        return None
    try:
        if len(raw) > _PAGE_LABELS_MAX_BYTES:
            raise ValueError("too large")
        data = json.loads(raw)
        pages = validate_document_pages(
            data.get("pages") if isinstance(data, dict) else None, image_count
        )
        if pages is None:
            raise ValueError("does not match the page images")
    except ValueError as e:
        logger.error(
            "Image mode: ignoring page labels %s (%s); labelling by position", path, e
        )
        return None
    return pages


def _not_found(page_store_dir: str) -> PageImagesNotFoundError:
    return PageImagesNotFoundError(
        f"No page images found at '{page_store_dir}'. The document has "
        "not been extracted in image output mode (or its images were "
        "removed). Re-extract the document with cache bypass to "
        "regenerate them (re-extraction is billed per page).",
        page_store_dir=page_store_dir,
    )


def discover_page_images(fs: FileStorage, page_store_dir: str) -> list[tuple[int, str]]:
    """Discover persisted page images, ordered by integer page number.

    See ``_discover_page_set``, which also reports whether ``pages.json``
    was listed.
    """
    return _discover_page_set(fs, page_store_dir)[0]


def _discover_page_set(
    fs: FileStorage, page_store_dir: str
) -> tuple[list[tuple[int, str]], bool]:
    """Discover persisted page images, ordered by integer page number.

    Lists ``page_store_dir`` through FileStorage, keeps entries whose
    basename matches the shared ``PAGE_NUMBER_REGEX`` (others are logged
    and skipped), and validates the set is exactly 1..N.

    Returns:
        ``([(page_number, full_path), ...] sorted by page number, whether
        PAGE_LABELS_FILENAME was in the listing)``.

    Raises:
        PageImagesNotFoundError: directory missing or no page images in it.
        PageImageSetIncompleteError: duplicate or missing page numbers.
    """
    # Object-store backends serve listings from fsspec's directory cache in
    # long-lived worker processes; a page purged since the last listing would
    # still "exist" here and only blow up at read time. Refresh the cache
    # first so discovery reflects reality (no-op for backends without one).
    invalidate = getattr(getattr(fs, "fs", None), "invalidate_cache", None)
    if callable(invalidate):
        try:
            invalidate(page_store_dir)
        except Exception:  # pragma: no cover - cache refresh is best-effort
            logger.debug("Could not invalidate listing cache for %s", page_store_dir)

    try:
        entries = fs.ls(page_store_dir) if fs.exists(page_store_dir) else None
    except FileNotFoundError:
        entries = None
    if entries is None:
        raise _not_found(page_store_dir)

    pages: dict[int, str] = {}
    has_labels = False
    for entry in entries:
        name = PurePosixPath(str(entry)).name
        match = _PAGE_NAME_RE.fullmatch(name)
        if not match:
            has_labels = has_labels or name == PAGE_LABELS_FILENAME
            logger.debug("Skipping non-page entry in %s: %s", page_store_dir, name)
            continue
        page_number = int(match.group(1))
        if page_number in pages:
            raise PageImageSetIncompleteError(
                f"Duplicate page number {page_number} in '{page_store_dir}' "
                f"({PurePosixPath(pages[page_number]).name} vs {name}); the "
                "page set is corrupt. Re-extract the document with cache "
                "bypass (billed per page).",
                page_store_dir=page_store_dir,
                found_pages=sorted(pages),
                missing_pages=[],
            )
        pages[page_number] = str(entry)

    if not pages:
        raise _not_found(page_store_dir)

    found = sorted(pages)
    missing = sorted(set(range(1, found[-1] + 1)) - set(found))
    if missing:
        raise PageImageSetIncompleteError(
            f"Only {len(found)} of {found[-1]} page images are present at "
            f"'{page_store_dir}' (missing pages: {missing[:10]}"
            f"{'…' if len(missing) > 10 else ''}). Re-extract the document "
            "with cache bypass to regenerate them (billed per page).",
            page_store_dir=page_store_dir,
            found_pages=found,
            missing_pages=missing,
        )

    return [(number, pages[number]) for number in found], has_labels


def load_page_images(  # noqa: C901 - fixed-cap and policy paths share one bounded-read loop
    fs: FileStorage,
    page_store_dir: str,
    *,
    limits: "ImageModePolicy | None" = None,
    prompt_text_bytes: int | None = None,
    page_cap: int | None | _UseConfigured = USE_CONFIGURED,
    max_total_bytes: int | None | _UseConfigured = USE_CONFIGURED,
) -> list[LoadedPageImage]:
    """Discover, cap-check, read, and base64-encode all page images.

    The page-count cap runs before any bytes are read so an oversized
    document fails fast and cheap. The aggregate byte budget is enforced
    with **bounded reads**: each page is read with a length limit of the
    remaining budget plus one byte, so no read — not even of a single
    pathological object — can ever allocate more than the budget in
    worker memory, regardless of the object's actual size or whether the
    backend exposes size metadata.

    ``limits`` is the model-aware ``ImageModePolicy`` for the LLM that will
    consume the pages (see ``unstract.sdk1.utils.image_limits``): it supplies
    the page budget, the raw-byte budget derived from the provider's
    request-size limit (``prompt_text_bytes`` sizes the text share of that
    request) and the per-image byte/pixel checks. Without it the
    fixed cap applies: ``None`` disables either; left unset, each is read
    from ``get_fixed_page_cap()`` / ``get_fixed_max_total_bytes()``.

    Raises:
        PageCapExceededError: more pages than the budget allows.
        PageImageSetTooLargeError: pages total more than the byte budget.
        PageImageTooLargeError: one page breaks a per-image limit.
        (plus the discovery errors from ``discover_page_images``)
    """
    if limits is not None and not (
        isinstance(page_cap, _UseConfigured)
        and isinstance(max_total_bytes, _UseConfigured)
    ):
        raise ValueError("pass either limits= or the fixed-cap page_cap/max_total_bytes")
    if limits is None:
        if isinstance(page_cap, _UseConfigured):
            page_cap = get_fixed_page_cap()
        if isinstance(max_total_bytes, _UseConfigured):
            max_total_bytes = get_fixed_max_total_bytes()
    discovered, has_labels = _discover_page_set(fs, page_store_dir)
    page_count = len(discovered)
    # Read first so a cap message can say the pages are a selection; only
    # when the listing has the file (most page sets have none).
    document_pages = (
        read_document_pages(fs, page_store_dir, page_count) if has_labels else None
    )
    selected = is_page_selection(document_pages)
    if limits is not None:
        # Imported here: the policy module imports this module's exceptions.
        from unstract.sdk1.utils.image_limits import policy as _policy

        page_cap = limits.page_budget.max_pages
        max_total_bytes = limits.raw_byte_budget(
            page_count=page_count, prompt_text_bytes=prompt_text_bytes
        )
        if page_count > page_cap:
            raise PageCapExceededError(
                _policy.page_cap_message(
                    page_count, limits.page_budget, charged=None, selected=selected
                ),
                page_store_dir=page_store_dir,
                page_count=page_count,
                page_cap=page_cap,
            )
    elif page_cap is not None and page_count > page_cap:
        from unstract.sdk1.utils.image_limits.policy import fixed_cap_message

        raise PageCapExceededError(
            fixed_cap_message(page_count, page_cap, selected=selected),
            page_store_dir=page_store_dir,
            page_count=page_count,
            page_cap=page_cap,
        )

    loaded = []
    total_bytes = 0
    for index, (page_number, path) in enumerate(discovered):
        read_kwargs: dict[str, int] = {}
        if max_total_bytes is not None:
            # Bounded read: never pull more than the remaining budget (+1
            # byte to detect the overflow) into memory — the hard
            # allocation ceiling for this loop is max_total_bytes + 1.
            read_kwargs["length"] = max_total_bytes - total_bytes + 1
        try:
            data = bytes(fs.read(path=path, mode="rb", **read_kwargs))
        except FileNotFoundError as e:
            # TOCTOU guard: the page vanished between discovery and read
            # (purged concurrently, or discovery served a stale listing).
            # Surface the typed incomplete-set error, never a raw IO error.
            raise PageImageSetIncompleteError(
                f"Page image {PurePosixPath(path).name} is missing from "
                f"'{page_store_dir}' (it disappeared after discovery); the "
                "page set is incomplete. Re-extract the document with cache "
                "bypass to regenerate it (billed per page).",
                page_store_dir=page_store_dir,
                found_pages=[n for n, _ in discovered if n != page_number],
                missing_pages=[page_number],
            ) from e
        total_bytes += len(data)
        if limits is not None:
            _policy.check_page_image(
                limits,
                page_number=page_number,
                page_count=page_count,
                data=data,
                page_store_dir=page_store_dir,
                document_page=document_pages[index] if document_pages else None,
            )
        if max_total_bytes is not None and total_bytes > max_total_bytes:
            # Stop before encoding/retaining more — the page cap bounds the
            # count, this bounds the payload.
            if limits is not None:
                message = _policy.request_too_large_message(
                    limits,
                    page_count=page_count,
                    raw_total=total_bytes,
                    prompt_text_bytes=prompt_text_bytes,
                    charged=None,
                )
            else:
                where = _page_position(
                    index, page_number, len(discovered), document_pages
                )
                message = (
                    "This document is too large for image output mode. Its "
                    "page images go over the "
                    f"{max_total_bytes / (1024 * 1024):.1f} MiB limit at {where}"
                    ", and image mode has to "
                    "send every page to the LLM in one request. Split the "
                    "document into smaller files, or use a text output mode "
                    "instead."
                )
            raise PageImageSetTooLargeError(
                message,
                page_store_dir=page_store_dir,
                total_bytes=total_bytes,
                max_total_bytes=max_total_bytes,
            )
        encoded = base64.b64encode(data).decode("ascii")
        loaded.append(
            LoadedPageImage(
                page_number=page_number,
                path=path,
                base64_data=encoded,
                document_page=document_pages[index] if document_pages else None,
            )
        )
    return loaded


def build_vision_message_content(
    pages: list[LoadedPageImage], prompt_text: str
) -> list[dict]:
    """Shape multimodal content blocks for ``LLM.complete_vision``.

    Layout: the prompt text first (task framing), then for each page — in
    page order — a ``Page N`` text label immediately followed by that
    page's image block. The explicit labels preserve reading order for the
    model and enable page citations later at zero cost. ``N`` is the page's
    number in the source document (``Page 10`` for document page 10 of a
    'Pages to extract' selection), as /whisper's page separators use, falling
    back to the image position when no labels were recorded.

    Returns the ``content`` list for a single user message; callers wrap it
    as ``[{"role": "user", "content": content}]``.
    """
    content: list[dict] = [{"type": "text", "text": prompt_text}]
    for page in pages:
        content.append({"type": "text", "text": f"Page {page.label_page}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{page.base64_data}",
                },
            }
        )
    return content
