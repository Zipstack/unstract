"""Which copy of the limits table a process uses, and keeping it fresh.

The source of truth is ``limits.json`` on the main branch of
Zipstack/unstract. Installs fetch that raw file so a data fix reaches them
without a release; the copy bundled in this package is the fallback that is
always available. Precedence, highest first:

1. ``VLM_IMAGE_LIMITS_FILE`` — operator override file, applied per provider
   on top of whichever base table is in use.
2. The remote copy (``VLM_IMAGE_LIMITS_URL``, default main on GitHub), when
   the last good fetch passed the same strict schema as the bundled file.
3. The bundled copy.

Fetching is bounded so image mode never waits long on GitHub: at most one
attempt per process per refresh window (failures included), a short
timeout and size cap per attempt, and while one thread fetches the others
keep serving the last good table. A fetch failure, a bad file or no
network logs a warning and keeps the last good copy; nothing here raises.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import httpx
from unstract.sdk1.utils.image_limits._schema import (
    LIMITS_OVERRIDE_FILE_ENV,
    IncompatibleSchemaError,
    LimitsSchemaError,
    LimitsTable,
    apply_override_file,
    load_limits_table,
    parse_limits_bytes,
)

logger = logging.getLogger(__name__)

# Empty string disables the fetch (air-gapped installs).
LIMITS_URL_ENV = "VLM_IMAGE_LIMITS_URL"
DEFAULT_LIMITS_URL = (
    "https://raw.githubusercontent.com/Zipstack/unstract/main/unstract/sdk1/"
    "src/unstract/sdk1/utils/image_limits/limits.json"
)
LIMITS_REFRESH_ENV = "VLM_IMAGE_LIMITS_REFRESH_SECONDS"
DEFAULT_REFRESH_SECONDS = 3600
# Floor on the window so a misconfigured value cannot hammer GitHub.
MIN_REFRESH_SECONDS = 60
# Whole-download budget for one attempt (connect + headers + body).
FETCH_TIMEOUT_SECONDS = 3.0
# The bundled file is ~80 KB; anything far larger is not a limits table.
MAX_REMOTE_BYTES = 1_000_000

# Seams for tests: the clock and the HTTP client.
_clock = time.monotonic


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True)


def configured_limits_url() -> str | None:
    """The remote table's URL, or None when the fetch is disabled."""
    raw = os.environ.get(LIMITS_URL_ENV)
    if raw is None:
        return DEFAULT_LIMITS_URL
    return raw.strip() or None


def configured_refresh_seconds() -> int:
    """Seconds between fetch attempts; bad values fall back to the default."""
    raw = os.environ.get(LIMITS_REFRESH_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_REFRESH_SECONDS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        logger.warning(
            "Ignoring %s=%r (not a positive integer); refreshing every %ss",
            LIMITS_REFRESH_ENV,
            raw,
            DEFAULT_REFRESH_SECONDS,
        )
        return DEFAULT_REFRESH_SECONDS
    return max(value, MIN_REFRESH_SECONDS)


class RemoteFetchError(Exception):
    """The remote file could not be downloaded within the limits."""


def fetch_remote_bytes(url: str) -> bytes:
    """Download ``url`` within ``FETCH_TIMEOUT_SECONDS`` and ``MAX_REMOTE_BYTES``."""
    deadline = _clock() + FETCH_TIMEOUT_SECONDS
    chunks: list[bytes] = []
    size = 0
    with _http_client() as client, client.stream("GET", url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_REMOTE_BYTES:
                raise RemoteFetchError(f"response is over {MAX_REMOTE_BYTES} bytes")
            if _clock() > deadline:
                raise RemoteFetchError(
                    f"download took longer than {FETCH_TIMEOUT_SECONDS:g}s"
                )
            chunks.append(chunk)
    return b"".join(chunks)


@dataclass
class _RemoteState:
    table: LimitsTable | None = None  # last good remote copy
    last_attempt: float | None = None


_lock = threading.Lock()
_bundled: LimitsTable | None = None
_remote: dict[str, _RemoteState] = {}
# override path -> (base table it was applied to, merged table)
_with_override: dict[str, tuple[LimitsTable, LimitsTable]] = {}
_logged_disabled = False


def _bundled_table() -> LimitsTable:
    global _bundled
    if _bundled is None:
        _bundled = load_limits_table()
    return _bundled


def _describe(table: LimitsTable) -> str:
    origin = table.origin
    if origin is None:
        return "limits table"
    return (
        f"{origin.source} limits table from {origin.location} (schema_version "
        f"{origin.schema_version}, verified_on {origin.verified_on}, sha256 "
        f"{origin.sha256})"
    )


def _refresh(url: str, state: _RemoteState) -> None:
    keeping = _describe(state.table or _bundled_table())
    try:
        table = parse_limits_bytes(fetch_remote_bytes(url), source="remote", location=url)
    except IncompatibleSchemaError as e:
        logger.warning(
            "Skipping image limits from %s: %s. Keeping the %s.", url, e, keeping
        )
        return
    except LimitsSchemaError as e:
        logger.warning(
            "Rejected image limits from %s (failed validation): %s. Keeping the %s.",
            url,
            e,
            keeping,
        )
        return
    except (httpx.HTTPError, RemoteFetchError) as e:
        logger.warning(
            "Could not fetch image limits from %s: %s. Keeping the %s.",
            url,
            e,
            keeping,
        )
        return
    except Exception:  # never let a refresh break image mode
        logger.warning(
            "Unexpected error fetching image limits from %s. Keeping the %s.",
            url,
            keeping,
            exc_info=True,
        )
        return
    previous = state.table
    state.table = table
    if previous is None or previous.origin != table.origin:
        logger.info("Using the %s", _describe(table))


def _base_table() -> LimitsTable:
    global _logged_disabled
    url = configured_limits_url()
    if url is None:
        bundled = _bundled_table()
        if not _logged_disabled:
            _logged_disabled = True
            logger.info(
                "Remote image limits disabled (%s is empty); using the %s",
                LIMITS_URL_ENV,
                _describe(bundled),
            )
        return bundled
    state = _remote.setdefault(url, _RemoteState())
    window = configured_refresh_seconds()

    def due() -> bool:
        return state.last_attempt is None or _clock() - state.last_attempt >= window

    # Non-blocking: if another thread is fetching, serve the last good copy.
    if due() and _lock.acquire(blocking=False):
        try:
            if due():
                state.last_attempt = _clock()
                _refresh(url, state)
        finally:
            _lock.release()
    return state.table or _bundled_table()


def _apply_override(base: LimitsTable, path: str) -> LimitsTable:
    cached = _with_override.get(path)
    if cached is not None and cached[0] is base:
        return cached[1]
    try:
        merged = apply_override_file(base, path)
        logger.info("Applied image-limits override file %s", path)
    except (OSError, ValueError) as e:  # LimitsSchemaError is a ValueError
        logger.error(
            "Ignoring image-limits override file %s (%s): %s",
            path,
            LIMITS_OVERRIDE_FILE_ENV,
            e,
        )
        merged = base
    _with_override[path] = (base, merged)
    return merged


def get_limits_table() -> LimitsTable:
    """The effective table: override file over the remote copy or bundled one."""
    base = _base_table()
    override = os.getenv(LIMITS_OVERRIDE_FILE_ENV) or None
    if override is None:
        return base
    return _apply_override(base, override)


def clear_limits_cache() -> None:
    """Forget every cached table and fetch time (tests)."""
    global _bundled, _logged_disabled
    with _lock:
        _bundled = None
        _remote.clear()
        _with_override.clear()
        _logged_disabled = False
