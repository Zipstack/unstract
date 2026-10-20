"""Which copy of the limits table a process uses, and keeping it fresh.

The source of truth is ``limits.json`` on the main branch of
Zipstack/unstract. Installs fetch that raw file so a data fix reaches them
without a release; the copy bundled in this package is the fallback that is
always available. Precedence, highest first:

1. ``VLM_IMAGE_LIMITS_FILE`` — operator override file, applied per provider
   on top of whichever base table is in use.
2. The remote copy (``VLM_IMAGE_LIMITS_URL``, default main on GitHub), when
   the last good fetch passed the same strict schema as the bundled file
   and stays within what a data refresh may change (``_loosened_limits``):
   every bundled provider kept with the same ``kind``, and no enforced
   image-count or request-byte limit raised above
   ``MAX_REMOTE_RAISE_FACTOR`` times the bundled value. Lowering a limit and
   adding providers or models are always accepted.
3. The bundled copy.

The operator override file is trusted as configuration: these remote
checks never apply to it.

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

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from unstract.sdk1.utils.image_limits._schema import (
    BUNDLED_LIMITS_PATH,
    LIMITS_OVERRIDE_FILE_ENV,
    FieldValue,
    IncompatibleSchemaError,
    LimitsSchemaError,
    LimitsTable,
    OverrideEntry,
    ProviderEntry,
    apply_override_file,
    load_limits_table,
    parse_limits_bytes,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from unstract.sdk1.utils.image_limits.resolve import LimitValue

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

# How far a remote copy may raise an enforced image-count or request-byte
# limit over the bundled value (product decision, UN-4427). A data fix that
# needs more than this ships in an sdk1 release. Lowering is unlimited.
MAX_REMOTE_RAISE_FACTOR = 2
# The enforced limits a remote copy may raise only that far.
GUARDED_FIELDS: tuple[str, ...] = ("max_images_per_request", "max_request_bytes")
HOSTED_KIND = "hosted"
# Rejection reasons quoted in one log line; the rest are counted.
_MAX_REASONS_LOGGED = 5

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
_known_ids: dict[str, tuple[str, ...]] | None = None


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


def _raw_value(field_value: FieldValue | LimitValue | None) -> int | None:
    """A count, or a byte limit as raw bytes (base64-counted limits are 3/4).

    Takes a table field or a resolved limit (both carry name, value and
    ``base64_counted``).
    """
    if field_value is None or field_value.value is None:
        return None
    if field_value.name == "max_request_bytes" and field_value.base64_counted:
        return field_value.value * 3 // 4
    return field_value.value


def _entry_value(
    table: LimitsTable,
    provider: ProviderEntry,
    override: OverrideEntry | None,
    name: str,
) -> int | None:
    """What a model matched by ``override`` (None: no override) is held to.

    Mirrors the resolver's field order (override fields over an inherited
    provider's defaults over the provider's defaults, then the table's
    ``default``) without needing a model id.
    """
    fields = dict(provider.defaults)
    if override is not None:
        parent = table.providers.get(override.inherit) if override.inherit else None
        if parent is not None:
            fields.update(parent.defaults)
        fields.update(override.fields)
    value = fields.get(name)
    if value is None or value.value is None:
        value = table.default.get(name)
    return _raw_value(value)


def _field_label(name: str) -> str:
    return f"{name} (raw bytes)" if name == "max_request_bytes" else name


def _raised_too_far(before: int | None, after: int | None) -> bool:
    if before is None:
        return False  # nothing was enforced, so nothing can loosen
    return after is None or after > MAX_REMOTE_RAISE_FACTOR * before


def _known_model_ids() -> dict[str, tuple[str, ...]]:
    """Example model ids per provider from the bundled file's ``vision_models``.

    Documentation-only data the parser does not keep; read here so a remote
    copy can be checked against how real models resolve, not just entry by
    entry (a new, earlier override can shadow an existing one).
    """
    global _known_ids
    if _known_ids is None:
        ids: dict[str, tuple[str, ...]] = {}
        try:
            data = json.loads(BUNDLED_LIMITS_PATH.read_bytes())
            for key, entry in data.get("providers", {}).items():
                families = (entry.get("vision_models") or {}).get("families") or {}
                examples = [
                    str(model)
                    for family in families.values()
                    for model in (family.get("examples") or [])
                ]
                ids[key] = tuple(dict.fromkeys(examples))
        except (OSError, ValueError, AttributeError, TypeError):
            logger.warning("Could not read the bundled model examples", exc_info=True)
        _known_ids = ids
    return _known_ids


def _loosened_by_entry(table: LimitsTable) -> Iterator[str]:
    """Kind changes and over-raised limits, provider entry by entry."""
    bundled = _bundled_table()
    for key, shipped in bundled.providers.items():
        remote = table.providers.get(key)
        if remote is None:
            continue  # reported by ``_dropped_providers``
        if remote.kind != shipped.kind:
            yield f"{key}: kind changed from {shipped.kind} to {remote.kind}"
            continue
        if shipped.kind != HOSTED_KIND:
            continue
        remote_overrides = {o.pattern: o for o in remote.overrides}
        entries: list[tuple[str, OverrideEntry | None]] = [("defaults", None)]
        entries += [(f"override {o.pattern!r}", o) for o in shipped.overrides]
        for label, shipped_override in entries:
            # An override the remote copy removed (or re-patterned) leaves
            # its models on the provider defaults.
            remote_override = (
                remote_overrides.get(shipped_override.pattern)
                if shipped_override is not None
                else None
            )
            for name in GUARDED_FIELDS:
                before = _entry_value(bundled, shipped, shipped_override, name)
                after = _entry_value(table, remote, remote_override, name)
                if _raised_too_far(before, after):
                    yield f"{key} {label}: {_field_label(name)} {before} -> {after}"


def _loosened_for_known_models(table: LimitsTable) -> Iterator[str]:
    """Over-raised (or no longer enforced) limits of the bundled example models."""
    # Imported here: ``resolve`` imports this module.
    from unstract.sdk1.utils.image_limits.resolve import resolve_image_limits

    bundled = _bundled_table()
    for key, model_ids in _known_model_ids().items():
        if key not in bundled.providers or key not in table.providers:
            continue
        for model_id in model_ids:
            before = resolve_image_limits(key, model_id, table=bundled)
            after = resolve_image_limits(key, model_id, table=table)
            for name in GUARDED_FIELDS:
                old, new = before.field(name), after.field(name)
                if old.advisory or old.value is None:
                    continue  # not enforced in the bundled table
                old_raw = _raw_value(old)
                new_raw = None if new.advisory else _raw_value(new)
                if _raised_too_far(old_raw, new_raw):
                    yield (
                        f"{key} model {model_id!r}: {_field_label(name)} "
                        f"{old_raw} -> {new_raw}"
                    )


def _loosened_limits(table: LimitsTable) -> list[str]:
    """Why ``table`` loosens enforcement beyond what a refresh may change.

    A provider's ``kind`` may not change (hosted -> pass_through would make
    its default-filled limits advisory), and an enforced image-count or
    request-byte limit (raw-byte equivalent) may not rise above
    ``MAX_REMOTE_RAISE_FACTOR`` times its bundled value, whether in a
    provider's defaults, an override, the table ``default`` it falls back
    to, or how a bundled example model resolves. Lowering is always fine,
    as are new providers and overrides that leave existing models alone.
    """
    reasons = list(dict.fromkeys(_loosened_by_entry(table)))
    reasons += [r for r in _loosened_for_known_models(table) if r not in reasons]
    return reasons


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
    loosened = _loosened_limits(table)
    if loosened:
        shown = "; ".join(loosened[:_MAX_REASONS_LOGGED])
        more = len(loosened) - _MAX_REASONS_LOGGED
        if more > 0:
            shown += f"; and {more} more"
        logger.warning(
            "Rejected image limits from %s: it loosens enforced limits more "
            "than a data refresh may (kind changes, or image-count/request-byte "
            "limits above %sx the bundled value): %s. Lowering limits and adding "
            "providers or models is accepted; larger raises ship in an sdk1 "
            "release. Keeping the %s.",
            url,
            MAX_REMOTE_RAISE_FACTOR,
            shown,
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
    global _bundled, _logged_disabled, _known_ids
    with _lock:
        _bundled = None
        _known_ids = None
        _remote.clear()
        _with_override.clear()
        _logged_disabled = False
