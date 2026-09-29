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
import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from unstract.sdk1.adapters.x2text.constants import ImageOutputConstants
from unstract.sdk1.file_storage import FileStorage

logger = logging.getLogger(__name__)

# Conservative default; effective value is supplied by the caller
# (platform-configured), this is only the fallback.
DEFAULT_PAGE_CAP = 20

# Aggregate raw-byte budget across all loaded pages. The page cap bounds the
# COUNT of images, not their size — without a byte budget, unusually large
# renders would grow worker memory and the provider request unbounded
# (base64 adds ~33% on top). 50MB raw comfortably exceeds any normal
# LLMWhisperer render while staying inside provider request limits.
DEFAULT_MAX_TOTAL_BYTES = 50 * 1024 * 1024

_PAGE_NAME_RE = re.compile(ImageOutputConstants.PAGE_NUMBER_REGEX)


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


@dataclass(frozen=True)
class LoadedPageImage:
    """A page image read from FileStorage, base64-encoded for a VLM call."""

    page_number: int
    path: str
    base64_data: str


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

    Lists ``page_store_dir`` through FileStorage, keeps entries whose
    basename matches the shared ``PAGE_NUMBER_REGEX`` (others are logged
    and skipped), and validates the set is exactly 1..N.

    Returns:
        ``[(page_number, full_path), ...]`` sorted by page number.

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
    for entry in entries:
        name = PurePosixPath(str(entry)).name
        match = _PAGE_NAME_RE.fullmatch(name)
        if not match:
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

    return [(number, pages[number]) for number in found]


def load_page_images(
    fs: FileStorage,
    page_store_dir: str,
    *,
    page_cap: int | None = DEFAULT_PAGE_CAP,
    max_total_bytes: int | None = DEFAULT_MAX_TOTAL_BYTES,
) -> list[LoadedPageImage]:
    """Discover, cap-check, read, and base64-encode all page images.

    The page-count cap runs before any bytes are read so an oversized
    document fails fast and cheap. The aggregate byte budget is enforced
    with **bounded reads**: each page is read with a length limit of the
    remaining budget plus one byte, so no read — not even of a single
    pathological object — can ever allocate more than the budget in
    worker memory, regardless of the object's actual size or whether the
    backend exposes size metadata. ``None`` disables either limit.

    Raises:
        PageCapExceededError: more pages than ``page_cap`` allows.
        PageImageSetTooLargeError: pages total more than ``max_total_bytes``.
        (plus the discovery errors from ``discover_page_images``)
    """
    discovered = discover_page_images(fs, page_store_dir)
    if page_cap is not None and len(discovered) > page_cap:
        raise PageCapExceededError(
            f"Document exceeds {page_cap} pages for image output mode "
            f"({len(discovered)} pages found). Reduce the page range (e.g. "
            "via the adapter's 'pages to extract' setting) or raise the "
            "configured page cap.",
            page_store_dir=page_store_dir,
            page_count=len(discovered),
            page_cap=page_cap,
        )

    loaded = []
    total_bytes = 0
    for page_number, path in discovered:
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
        if max_total_bytes is not None and total_bytes > max_total_bytes:
            # Stop before encoding/retaining more — the page cap bounds the
            # count, this bounds the payload.
            raise PageImageSetTooLargeError(
                f"Page images total more than "
                f"{max_total_bytes // (1024 * 1024)}MB by page {page_number} "
                f"of {len(discovered)} — too large to send to the LLM in "
                "one request. Reduce the page range (e.g. via the adapter's "
                "'pages to extract' setting).",
                page_store_dir=page_store_dir,
                total_bytes=total_bytes,
                max_total_bytes=max_total_bytes,
            )
        encoded = base64.b64encode(data).decode("ascii")
        loaded.append(
            LoadedPageImage(page_number=page_number, path=path, base64_data=encoded)
        )
    return loaded


def build_vision_message_content(
    pages: list[LoadedPageImage], prompt_text: str
) -> list[dict]:
    """Shape multimodal content blocks for ``LLM.complete_vision``.

    Layout: the prompt text first (task framing), then for each page — in
    page order — a ``Page N`` text label immediately followed by that
    page's image block. The explicit labels preserve reading order for the
    model and enable page citations later at zero cost.

    Returns the ``content`` list for a single user message; callers wrap it
    as ``[{"role": "user", "content": content}]``.
    """
    content: list[dict] = [{"type": "text", "text": prompt_text}]
    for page in pages:
        content.append({"type": "text", "text": f"Page {page.page_number}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{page.base64_data}",
                },
            }
        )
    return content
