"""Which copy of the limits table a process uses, and keeping it fresh.

The source of truth is ``limits.json`` on the main branch of
Zipstack/unstract. By default a process uses only the copy bundled in this
package and never fetches anything (on-prem installs never phone home). A
deployment that wants data fixes without a release (SaaS) opts in by setting
``VLM_IMAGE_LIMITS_URL`` to ``PUBLISHED_LIMITS_URL``, the raw file on main;
the bundled copy stays the fallback that is always available. Precedence,
highest first:

1. ``VLM_IMAGE_LIMITS_FILE`` — operator override file, applied per provider
   on top of whichever base table is in use.
2. The remote copy (``VLM_IMAGE_LIMITS_URL``; unset or empty, the default,
   means no fetch), when the last good fetch passed the same strict schema
   as the bundled file.
   What a remote copy may change is enforced at lookup time, not here:
   ``resolve.resolve_image_limits`` clamps every remote-table result
   against the bundled table (bundled ``kind``; image-count and
   request-byte limits at most ``MAX_REMOTE_RAISE_FACTOR`` times the
   bundled value). A provider the remote copy lacks resolves from the
   bundled entry, also as the ``inherit`` parent of an override-file
   entry. So a bad value on main is capped per model, and every
   other change in the same file (tightening, new models and providers)
   still reaches installs.
3. The bundled copy.

The operator override file is trusted as configuration: the clamp never
applies to a field or provider entry it supplies.

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

# Unset or empty (the default) disables the fetch: only the bundled table is
# used. SaaS opts in by setting it to ``PUBLISHED_LIMITS_URL``.
LIMITS_URL_ENV = "VLM_IMAGE_LIMITS_URL"
PUBLISHED_LIMITS_URL = (
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
# The bundled file is ~90 KB; anything far larger is not a limits table.
MAX_REMOTE_BYTES = 1_000_000

# How far a remote copy may loosen an enforced image-count, byte or pixel
# limit over the bundled value (product decision, UN-4427). A data fix that
# needs more than this ships in an sdk1 release. Tightening is unlimited.
# Applied at lookup time (``resolve._clamp_to_bundled``).
MAX_REMOTE_RAISE_FACTOR = 2
# The enforced limits a remote copy may loosen only that far. Raising
# ``many_images_threshold`` (or removing it) loosens too: fewer requests
# get the smaller ``many_images_max_px``.
GUARDED_FIELDS: tuple[str, ...] = (
    "max_images_per_request",
    "max_request_bytes",
    "max_image_bytes",
    "max_image_px",
    "many_images_threshold",
    "many_images_max_px",
)
REMOTE_SOURCE = "remote"

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
    """The remote table's URL, or None (unset or empty: the default) for no fetch."""
    return os.environ.get(LIMITS_URL_ENV, "").strip() or None


def configured_refresh_seconds() -> int:
    """Seconds between fetch attempts; bad values fall back to the default.

    Read on every refreshing lookup, so a bad value is logged once per
    process.
    """
    global _logged_bad_refresh
    raw = os.environ.get(LIMITS_REFRESH_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_REFRESH_SECONDS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        if _logged_bad_refresh:
            return DEFAULT_REFRESH_SECONDS
        _logged_bad_refresh = True
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

    The body is abandoned at the first chunk that arrives more than
    ``FETCH_TIMEOUT_SECONDS`` after the call started; ``_fetch_with_deadline``
    bounds the whole call, DNS and a stalled stream included.
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


@dataclass(frozen=True)
class _OverrideResult:
    base: LimitsTable  # the base table the file was applied to
    signature: tuple[int, int] | None  # the file's (mtime_ns, size); None: no stat
    merged: LimitsTable  # the result; ``base`` itself when the file failed
    failed_at: float | None  # clock time of a failed read or parse, else None


# A failed override file is retried at most this often even when its
# (mtime, size) has not changed, so a transient read error is not kept for
# the life of the process and a persistent one logs at most once a minute.
OVERRIDE_RETRY_SECONDS = 60


@dataclass
class _RemoteState:
    table: LimitsTable | None = None  # last good remote copy
    last_attempt: float | None = None


_lock = threading.Lock()
_bundled: LimitsTable | None = None
_remote: dict[str, _RemoteState] = {}
# override path -> the last application of that file (see ``_apply_override``)
_with_override: dict[str, _OverrideResult] = {}
_logged_disabled = False
# (provider, model, field) clamps already logged by this process.
_clamp_reported: set[tuple[str, str, str]] = set()
# Providers this process has logged as missing from a non-bundled table.
_missing_reported: set[str] = set()
_clamp_lock = threading.Lock()
# Whether this process has logged a bad refresh-window setting.
_logged_bad_refresh = False


def bundled_table() -> LimitsTable:
    """The copy shipped in this package (never fetched, never overridden)."""
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


def _first_time(seen: set, key: object) -> bool:
    """True, and remember ``key``, the first time ``seen`` is asked about it."""
    with _clamp_lock:
        if key in seen:
            return False
        seen.add(key)
        return True


def first_clamp_report(key: tuple[str, str, str]) -> bool:
    """True the first time this process clamps ``(provider, model, field)``.

    Keeps the clamp warning to one line per field per process: lookups run
    per page set and per profile render.
    """
    return _first_time(_clamp_reported, key)


def first_missing_provider_report(provider: str) -> bool:
    """True the first time this process falls back to bundled for ``provider``.

    The fallback (``resolve._resolve_on``, and an ``inherit`` whose parent the
    effective table lacks) runs on every lookup; one WARNING per provider
    per process is enough.
    """
    return _first_time(_missing_reported, provider)


def _refresh(url: str, state: _RemoteState) -> None:
    keeping = _describe(state.table or bundled_table())
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
        bundled = bundled_table()
        if not _logged_disabled:
            _logged_disabled = True
            logger.info(
                "Remote image limits off (%s unset or empty); using the %s",
                LIMITS_URL_ENV,
                _describe(bundled),
            )
        return bundled
    state = _remote.setdefault(url, _RemoteState())
    if refresh:
        _maybe_start_refresh(url, state)
    return state.table or bundled_table()


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


def _file_signature(path: str) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _apply_override(base: LimitsTable, path: str) -> LimitsTable:
    """``base`` with the override file at ``path`` applied, cached per file.

    The cached result is reused while the base table and the file's
    ``(mtime, size)`` are unchanged, so an operator can fix or replace the
    file without restarting the process. A failed read or parse falls back
    to ``base`` and is retried when the file changes, or after
    ``OVERRIDE_RETRY_SECONDS`` at the latest; it is never kept for good.
    """
    signature = _file_signature(path)
    cached = _with_override.get(path)
    if (
        cached is not None
        and cached.base is base
        and cached.signature == signature
        and (
            cached.failed_at is None
            or _clock() - cached.failed_at < OVERRIDE_RETRY_SECONDS
        )
    ):
        return cached.merged
    failed_at: float | None = None
    try:
        # Inherit targets may name a bundled provider the base (remote) copy
        # dropped; the lookup resolves such a parent from the bundled entry.
        merged = apply_override_file(base, path, bundled=bundled_table())
        logger.info("Applied image-limits override file %s", path)
    except (OSError, ValueError) as e:  # LimitsSchemaError is a ValueError
        logger.error(
            "Ignoring image-limits override file %s (%s): %s",
            path,
            LIMITS_OVERRIDE_FILE_ENV,
            e,
        )
        merged, failed_at = base, _clock()
    except Exception:  # a bad override must never break image mode
        logger.error(
            "Ignoring image-limits override file %s (%s): unexpected error",
            path,
            LIMITS_OVERRIDE_FILE_ENV,
            exc_info=True,
        )
        merged, failed_at = base, _clock()
    _with_override[path] = _OverrideResult(base, signature, merged, failed_at)
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
    global _bundled, _logged_disabled, _logged_bad_refresh
    with _lock:
        _bundled = None
        _remote.clear()
        _with_override.clear()
        _logged_disabled = False
        _logged_bad_refresh = False
    with _clamp_lock:
        _clamp_reported.clear()
        _missing_reported.clear()
