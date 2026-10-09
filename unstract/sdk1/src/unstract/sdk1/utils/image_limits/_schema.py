"""Strict loader for the bundled vision image-limits table (``limits.json``).

The table is data, so the loader is unforgiving: unknown keys, unresolved
source references, bad regexes and bad ``inherit`` targets are load errors.
A typo must never silently disable a limit. Documentation-only keys that
the data owners keep for maintainers (routing notes, model family counts)
are allowed and ignored.

Layers: the shipped file is loaded first; an operator override file named
by ``VLM_IMAGE_LIMITS_FILE`` may replace whole provider entries and/or the
``default`` block. Replacement is per provider, never a deep merge, so the
effective entry is always one file's text. Every entry records the layer
it came from so messages and logs can say where a number originated.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
BUNDLED_LIMITS_PATH = Path(__file__).with_name("limits.json")
# Operator override: absolute path to a JSON file in the same schema.
LIMITS_OVERRIDE_FILE_ENV = "VLM_IMAGE_LIMITS_FILE"

Layer = Literal["shipped", "override"]
Confidence = Literal["verified", "unverified"]

LIMIT_FIELDS: tuple[str, ...] = (
    "max_images_per_request",
    "max_request_bytes",
    "max_image_bytes",
    "max_image_px",
    "many_images_threshold",
    "many_images_max_px",
    "max_image_patches",
    "tokens_per_image",
    "max_input_tokens",
)
# Fields that fall back to the top-level ``default`` block when a provider
# resolves them to null. Per-image fields do not: null means "no check".
DEFAULTABLE_FIELDS: frozenset[str] = frozenset(
    {"max_images_per_request", "max_request_bytes", "tokens_per_image"}
)
_CONFIDENCES: frozenset[str] = frozenset({"verified", "unverified"})
_KINDS: frozenset[str] = frozenset({"hosted", "pass_through"})

_TOP_LEVEL_KEYS = frozenset({"_meta", "sources", "default", "providers"})
_SOURCE_KEYS = frozenset({"url", "verified_on", "quote", "note"})
_DEFAULT_DOC_KEYS = frozenset({"applies_to", "rationale", "note"})
_PROVIDER_DOC_KEYS = frozenset(
    {
        "litellm_model_prefix",
        "routing_note",
        "governed_by",
        "published_limit",
        "vision_models",
        "source",
        "note",
    }
)
_PROVIDER_KEYS = (
    frozenset({"adapter", "display_name", "kind", "defaults", "model_overrides"})
    | _PROVIDER_DOC_KEYS
)
_OVERRIDE_KEYS = frozenset({"pattern", "description", "note", "inherit"}) | set(
    LIMIT_FIELDS
)
_FIELD_KEYS = frozenset(
    {"value", "confidence", "source", "scope", "base64_counted", "note"}
)


class LimitsSchemaError(ValueError):
    """The limits file does not satisfy the schema contract."""


@dataclass(frozen=True)
class SourceEntry:
    key: str
    url: str
    verified_on: str | None


@dataclass(frozen=True)
class FieldValue:
    """One limit field as written in the file (not yet resolved)."""

    name: str
    value: int | None
    confidence: str
    sources: tuple[str, ...]
    base64_counted: bool  # absent in data -> True (the conservative reading)
    scope: str | None = None


@dataclass(frozen=True)
class OverrideEntry:
    pattern: str
    regex: re.Pattern[str]
    description: str | None
    inherit: str | None
    fields: dict[str, FieldValue]


@dataclass(frozen=True)
class ProviderEntry:
    key: str
    adapter: str
    display_name: str
    kind: str
    defaults: dict[str, FieldValue]
    overrides: tuple[OverrideEntry, ...]
    layer: Layer


@dataclass(frozen=True)
class LimitsTable:
    schema_version: int
    sources: dict[str, SourceEntry]
    default: dict[str, FieldValue]
    providers: dict[str, ProviderEntry]
    layer: Layer = "shipped"
    default_layer: Layer = "shipped"
    meta: dict[str, Any] = field(default_factory=dict)


def _fail(where: str, message: str) -> LimitsSchemaError:
    return LimitsSchemaError(f"{where}: {message}")


def _check_keys(where: str, data: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _fail(where, f"unknown key(s) {unknown}")


def _parse_field(  # noqa: C901 - one check per schema rule
    where: str, name: str, raw: object, sources: dict[str, SourceEntry]
) -> FieldValue:
    if name not in LIMIT_FIELDS:
        raise _fail(where, f"unknown limit field '{name}'")
    if not isinstance(raw, dict):
        raise _fail(where, f"limit field '{name}' must be an object")
    _check_keys(f"{where}.{name}", raw, _FIELD_KEYS)
    for required in ("value", "confidence", "source"):
        if required not in raw:
            raise _fail(f"{where}.{name}", f"missing '{required}'")
    value = raw["value"]
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise _fail(f"{where}.{name}", "value must be an integer or null")
    if value is not None and value <= 0:
        raise _fail(f"{where}.{name}", "value must be positive")
    confidence = raw["confidence"]
    if confidence not in _CONFIDENCES:
        raise _fail(
            f"{where}.{name}", f"confidence must be one of {sorted(_CONFIDENCES)}"
        )
    raw_sources = raw["source"]
    if raw_sources is None:
        source_keys: tuple[str, ...] = ()
    elif isinstance(raw_sources, str):
        source_keys = (raw_sources,)
    elif isinstance(raw_sources, list) and all(isinstance(s, str) for s in raw_sources):
        source_keys = tuple(raw_sources)
    else:
        raise _fail(f"{where}.{name}", "source must be a key, a list of keys or null")
    for key in source_keys:
        if key not in sources:
            raise _fail(f"{where}.{name}", f"unknown source key '{key}'")
    if value is not None and not source_keys:
        raise _fail(f"{where}.{name}", "a numeric value needs at least one source")
    base64_counted = raw.get("base64_counted", True)
    if not isinstance(base64_counted, bool):
        raise _fail(f"{where}.{name}", "base64_counted must be a boolean")
    return FieldValue(
        name=name,
        value=value,
        confidence=confidence,
        sources=source_keys,
        base64_counted=base64_counted,
        scope=raw.get("scope"),
    )


def _parse_fields(
    where: str,
    data: dict[str, Any],
    sources: dict[str, SourceEntry],
    skip: frozenset[str],
) -> dict[str, FieldValue]:
    return {
        name: _parse_field(where, name, raw, sources)
        for name, raw in data.items()
        if name not in skip
    }


def _parse_sources(raw: object) -> dict[str, SourceEntry]:
    if not isinstance(raw, dict):
        raise _fail("sources", "must be an object")
    parsed: dict[str, SourceEntry] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            raise _fail(f"sources.{key}", "must be an object")
        _check_keys(f"sources.{key}", entry, _SOURCE_KEYS)
        url = entry.get("url")
        if not isinstance(url, str) or not url.strip():
            raise _fail(f"sources.{key}", "url must be a non-empty string")
        verified_on = entry.get("verified_on")
        if verified_on is not None and not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", verified_on
        ):
            raise _fail(f"sources.{key}", "verified_on must be an ISO date")
        parsed[key] = SourceEntry(key=key, url=url, verified_on=verified_on)
    return parsed


def _parse_provider(  # noqa: C901 - one check per schema rule
    key: str, raw: object, sources: dict[str, SourceEntry], layer: Layer
) -> ProviderEntry:
    where = f"providers.{key}"
    if not isinstance(raw, dict):
        raise _fail(where, "must be an object")
    _check_keys(where, raw, _PROVIDER_KEYS)
    for required in ("adapter", "display_name", "kind"):
        if not isinstance(raw.get(required), str) or not raw[required]:
            raise _fail(where, f"'{required}' must be a non-empty string")
    if raw["kind"] not in _KINDS:
        raise _fail(where, f"kind must be one of {sorted(_KINDS)}")
    defaults_raw = raw.get("defaults", {})
    if not isinstance(defaults_raw, dict):
        raise _fail(f"{where}.defaults", "must be an object")
    defaults = _parse_fields(f"{where}.defaults", defaults_raw, sources, frozenset())
    overrides: list[OverrideEntry] = []
    for index, override_raw in enumerate(raw.get("model_overrides", []) or []):
        owhere = f"{where}.model_overrides[{index}]"
        if not isinstance(override_raw, dict):
            raise _fail(owhere, "must be an object")
        _check_keys(owhere, override_raw, _OVERRIDE_KEYS)
        pattern = override_raw.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise _fail(owhere, "'pattern' must be a non-empty string")
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise _fail(owhere, f"invalid regex pattern: {e}") from e
        inherit = override_raw.get("inherit")
        if inherit is not None and not isinstance(inherit, str):
            raise _fail(owhere, "'inherit' must be a provider key")
        fields = _parse_fields(
            owhere,
            override_raw,
            sources,
            frozenset({"pattern", "description", "note", "inherit"}),
        )
        overrides.append(
            OverrideEntry(
                pattern=pattern,
                regex=regex,
                description=override_raw.get("description"),
                inherit=inherit,
                fields=fields,
            )
        )
    return ProviderEntry(
        key=key,
        adapter=raw["adapter"],
        display_name=raw["display_name"],
        kind=raw["kind"],
        defaults=defaults,
        overrides=tuple(overrides),
        layer=layer,
    )


def _parse_table(  # noqa: C901 - one check per schema rule
    data: object, *, layer: Layer, require_default: bool = True
) -> LimitsTable:
    if not isinstance(data, dict):
        raise _fail("<root>", "must be an object")
    _check_keys("<root>", data, _TOP_LEVEL_KEYS)
    meta = data.get("_meta", {})
    if not isinstance(meta, dict):
        raise _fail("_meta", "must be an object")
    if meta.get("schema_version") != SCHEMA_VERSION:
        raise _fail(
            "_meta.schema_version",
            f"expected {SCHEMA_VERSION}, got {meta.get('schema_version')!r}",
        )
    sources = _parse_sources(data.get("sources", {}))
    default_raw = data.get("default")
    if default_raw is None:
        if require_default:
            raise _fail("default", "missing")
        default: dict[str, FieldValue] = {}
    else:
        if not isinstance(default_raw, dict):
            raise _fail("default", "must be an object")
        default = _parse_fields("default", default_raw, sources, _DEFAULT_DOC_KEYS)
        for name in DEFAULTABLE_FIELDS:
            if (
                require_default
                and default.get(
                    name, FieldValue(name, None, "unverified", (), True)
                ).value
                is None
            ):
                raise _fail("default", f"'{name}' must carry a numeric value")
    providers_raw = data.get("providers", {})
    if not isinstance(providers_raw, dict):
        raise _fail("providers", "must be an object")
    providers = {
        key: _parse_provider(key, raw, sources, layer)
        for key, raw in providers_raw.items()
    }
    for entry in providers.values():
        for override in entry.overrides:
            if override.inherit is not None and override.inherit not in providers:
                raise _fail(
                    f"providers.{entry.key}",
                    f"inherit target '{override.inherit}' is not a provider key",
                )
    return LimitsTable(
        schema_version=SCHEMA_VERSION,
        sources=sources,
        default=default,
        providers=providers,
        layer=layer,
        default_layer=layer,
        meta=meta,
    )


def _read_json(path: Path) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_limits_table(path: str | Path | None = None) -> LimitsTable:
    """Load and validate a limits file (the bundled one by default).

    Raises ``LimitsSchemaError`` on any contract violation; a malformed
    bundled file is a programming error that the test suite catches.
    """
    target = Path(path) if path is not None else BUNDLED_LIMITS_PATH
    try:
        data = _read_json(target)
    except (OSError, ValueError) as e:
        raise LimitsSchemaError(f"{target}: cannot read limits file: {e}") from e
    return _parse_table(data, layer="shipped")


def apply_override_file(table: LimitsTable, path: str | Path) -> LimitsTable:
    """Replace provider entries (and/or ``default``) from an override file.

    Per-provider replacement: a provider present in the override replaces
    the shipped entry wholesale; ``default`` likewise. Sources are merged so
    an override can cite its own evidence. The override must resolve on its
    own (its ``inherit`` targets may name shipped providers).
    """
    data = _read_json(Path(path))
    if not isinstance(data, dict):
        raise LimitsSchemaError(f"{path}: override must be an object")
    # Validate the override against the union of sources, and let its
    # inherit targets point at shipped providers.
    merged_sources = {
        **{
            k: {"url": v.url, "verified_on": v.verified_on}
            for k, v in table.sources.items()
        }
    }
    for key, entry in (data.get("sources") or {}).items():
        merged_sources[key] = entry
    candidate = dict(data)
    candidate["sources"] = merged_sources
    candidate.setdefault("_meta", {"schema_version": SCHEMA_VERSION})
    # Stub unknown inherit targets with the shipped providers so validation
    # of cross-layer inheritance succeeds; they are re-attached below.
    shipped_stubs = {
        key: {"adapter": p.adapter, "display_name": p.display_name, "kind": p.kind}
        for key, p in table.providers.items()
        if key not in (candidate.get("providers") or {})
    }
    candidate["providers"] = {**shipped_stubs, **(candidate.get("providers") or {})}
    parsed = _parse_table(candidate, layer="override", require_default=False)

    providers = dict(table.providers)
    for key in data.get("providers") or {}:
        providers[key] = parsed.providers[key]
    default = parsed.default if data.get("default") is not None else table.default
    default_layer: Layer = (
        "override" if data.get("default") is not None else table.default_layer
    )
    sources = dict(table.sources)
    sources.update(parsed.sources)
    return LimitsTable(
        schema_version=SCHEMA_VERSION,
        sources=sources,
        default=default,
        providers=providers,
        layer="override",
        default_layer=default_layer,
        meta=table.meta,
    )


@cache
def _cached_table(override_path: str | None) -> LimitsTable:
    table = load_limits_table()
    if override_path:
        try:
            table = apply_override_file(table, override_path)
            logger.info("Applied image-limits override file %s", override_path)
        except (OSError, ValueError, LimitsSchemaError) as e:
            logger.error(
                "Ignoring image-limits override file %s (%s): %s",
                override_path,
                LIMITS_OVERRIDE_FILE_ENV,
                e,
            )
    return table


def get_limits_table() -> LimitsTable:
    """The effective table for this process: bundled file + optional override."""
    override = os.getenv(LIMITS_OVERRIDE_FILE_ENV) or None
    return _cached_table(override)


def clear_limits_cache() -> None:
    """Drop the cached table (tests)."""
    _cached_table.cache_clear()
