"""Which copy of the limits table a process uses, and keeping it fresh.

The source of truth is ``limits.json`` on the main branch of
Zipstack/unstract. Installs fetch that raw file so a data fix reaches them
without a release; the copy bundled in this package is the fallback that is
always available. Precedence, highest first:

1. ``VLM_IMAGE_LIMITS_FILE`` — operator override file, applied per provider
   on top of whichever base table is in use.
2. The remote copy (``VLM_IMAGE_LIMITS_URL``, default main on GitHub), when
   the last good fetch passed the same strict schema as the bundled file
   and kept every provider the bundled file has.
3. The bundled copy.

No caller ever waits on GitHub: ``get_limits_table`` always answers from
memory (the last good remote copy, else the bundled one). When a refresh
is due it is started on a background daemon thread, at most one at a time
per process and at most one attempt per refresh window (failures
included). That attempt has an overall deadline of
``FETCH_TIMEOUT_SECONDS`` covering DNS, connect, headers and body, does
not follow redirects, and is capped at ``MAX_REMOTE_BYTES``. A fetch
failure, a bad file or no network logs a warning and keeps the last good
copy; nothing here raises.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from collections.abc import Callable

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
# Overall deadline for one attempt: DNS, connect, headers and body. Enforced
# by waiting on the fetch thread (``_fetch_with_deadline``), so a hung DNS
# lookup or a server that trickles bytes cannot stretch it.
FETCH_TIMEOUT_SECONDS = 3.0
# The bundled file is ~80 KB; anything far larger is not a limits table.
MAX_REMOTE_BYTES = 1_000_000

# Seams for tests: the clock, the HTTP client and how a refresh is started.
_clock = time.monotonic


def _http_client() -> httpx.Client:
    # No redirects: the URL is a raw file, and following one would restart
    # httpx's per-phase timers and point the fetch at another host.
    return httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False)


def _start_background(target: Callable[[], None]) -> None:
    """Run a refresh off the caller's thread (tests swap in a synchronous run)."""
    threading.Thread(target=target, name="image-limits-refresh", daemon=True).start()


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
    """Download ``url`` (no redirects), capped at ``MAX_REMOTE_BYTES``.

    The body is abandoned once ``FETCH_TIMEOUT_SECONDS`` have passed between
    chunks; ``_fetch_with_deadline`` bounds the whole call, DNS included.
    """
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


def _fetch_with_deadline(url: str) -> bytes:
    """``fetch_remote_bytes`` bounded by an overall ``FETCH_TIMEOUT_SECONDS``.

    httpx times each phase separately and DNS resolution not at all, so the
    download runs on its own daemon thread and is abandoned (its result
    discarded) when the deadline passes.
    """
    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            outcome["data"] = fetch_remote_bytes(url)
        except BaseException as e:  # re-raised on the waiting thread
            outcome["error"] = e

    worker = threading.Thread(target=run, name="image-limits-fetch", daemon=True)
    worker.start()
    worker.join(FETCH_TIMEOUT_SECONDS)
    if worker.is_alive():
        raise RemoteFetchError(f"no complete response within {FETCH_TIMEOUT_SECONDS:g}s")
    error = outcome.get("error")
    if error is not None:
        raise error  # type: ignore[misc]
    return outcome["data"]  # type: ignore[return-value]


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


def bundled_table() -> LimitsTable:
    """The copy shipped in this package (never fetched, never overridden)."""
    return _bundled_table()


def _dropped_providers(table: LimitsTable) -> list[str]:
    """Bundled provider keys the remote table no longer has."""
    return sorted(set(_bundled_table().providers) - set(table.providers))


def _refresh(url: str, state: _RemoteState) -> None:
    keeping = _describe(state.table or _bundled_table())
    try:
        table = parse_limits_bytes(
            _fetch_with_deadline(url), source="remote", location=url
        )
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
    dropped = _dropped_providers(table)
    if dropped:
        # A provider missing from the remote copy would resolve as an
        # advisory pass-through and lose every enforced limit, on every
        # install, within one refresh window. Treat it as a bad file.
        logger.warning(
            "Rejected image limits from %s: it drops provider(s) %s that the "
            "bundled table has. Keeping the %s.",
            url,
            dropped,
            keeping,
        )
        return
    previous = state.table
    state.table = table
    if previous is None or previous.origin != table.origin:
        logger.info("Using the %s", _describe(table))


def _base_table(*, refresh: bool = True) -> LimitsTable:
    """The last good remote copy, else the bundled one; never waits.

    ``refresh=True`` also starts a background refresh when one is due.
    """
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
    if refresh:
        _maybe_start_refresh(url, state)
    return state.table or _bundled_table()


def _maybe_start_refresh(url: str, state: _RemoteState) -> None:
    window = configured_refresh_seconds()

    def due() -> bool:
        return state.last_attempt is None or _clock() - state.last_attempt >= window

    # Non-blocking: if a refresh is already running, keep serving the last
    # good copy. The lock is held by the refresh until it finishes.
    if not (due() and _lock.acquire(blocking=False)):
        return
    if not due():
        _lock.release()
        return
    state.last_attempt = _clock()

    def run() -> None:
        try:
            _refresh(url, state)
        finally:
            _lock.release()

    try:
        _start_background(run)
    except Exception:  # e.g. the interpreter cannot start a thread
        _lock.release()
        logger.warning("Could not start the image-limits refresh", exc_info=True)


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
    except Exception:  # a bad override must never break image mode
        logger.error(
            "Ignoring image-limits override file %s (%s): unexpected error",
            path,
            LIMITS_OVERRIDE_FILE_ENV,
            exc_info=True,
        )
        merged = base
    _with_override[path] = (base, merged)
    return merged


def get_limits_table(*, refresh: bool = True) -> LimitsTable:
    """The effective table: override file over the remote copy or bundled one.

    Never waits on the network: it serves the last good remote copy this
    process holds, else the bundled one. ``refresh=True`` (the default) also
    starts a background refresh when the window is due; ``refresh=False``
    never starts one.
    """
    base = _base_table(refresh=refresh)
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
