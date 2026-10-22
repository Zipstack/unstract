"""Strict loader for the bundled vision image-limits table (``limits.json``).

The table is data, so the loader is unforgiving: unknown keys, unresolved
source references, bad regexes and bad ``inherit`` targets are load errors.
A typo must never silently disable a limit. Documentation-only keys that
the data owners keep for maintainers (routing notes, model family counts)
are allowed and ignored.

The same contract applies to every copy of the table: the bundled file,
the copy fetched from GitHub (``source.py``) and an operator override file.

Layers: the base table (remote copy, else bundled) is loaded first; an
operator override file named by ``VLM_IMAGE_LIMITS_FILE`` may replace whole
provider entries and/or fields of the ``default`` block. Providers are
replaced whole (no deep merge), so an effective provider entry is always
one file's text; ``default`` is merged field by field, so tightening one
default never drops the others. Every entry (and every default field)
records the layer it came from, and the table records its origin (source,
location, version), so messages and logs can say where a number originated.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

# The schema this sdk1 reads. Data-only edits keep it; any new key or
# changed meaning bumps it, and older installs then skip the remote copy.
SCHEMA_VERSION = 1
BUNDLED_LIMITS_PATH = Path(__file__).with_name("limits.json")
# Operator override: absolute path to a JSON file in the same schema.
LIMITS_OVERRIDE_FILE_ENV = "VLM_IMAGE_LIMITS_FILE"

# Longest accepted override regex. Patterns run against every lookup, and
# a remote copy must not be able to ship a pathological one.
MAX_PATTERN_LENGTH = 300

Layer = Literal["shipped", "override"]
TableSource = Literal["bundled", "remote"]

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


class IncompatibleSchemaError(LimitsSchemaError):
    """The file is written in a schema version this sdk1 does not read."""


@dataclass(frozen=True)
class TableOrigin:
    """Where the effective table came from, for logs and error messages."""

    source: TableSource
    location: str  # file path or URL
    schema_version: int
    verified_on: str | None  # the file's ``_meta.verified_on``
    sha256: str  # first 12 hex digits of the file's bytes
    override_file: str | None = None

    @property
    def version(self) -> str:
        """Short label such as ``2026-10-09 remote 1a2b3c4d5e6f``."""
        label = f"{self.verified_on or 'undated'} {self.source} {self.sha256}"
        if self.override_file:
            label += " + override file"
        return label


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
    origin: TableOrigin | None = None
    # Default fields an override file set (their layer is "override").
    default_override_fields: frozenset[str] = frozenset()

    def default_field_layer(self, name: str) -> Layer:
        """The layer a ``default`` field came from."""
        return "override" if name in self.default_override_fields else self.default_layer


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
        if len(pattern) > MAX_PATTERN_LENGTH:
            raise _fail(
                owhere,
                f"pattern is {len(pattern)} characters, over the "
                f"{MAX_PATTERN_LENGTH}-character limit",
            )
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
    version = meta.get("schema_version")
    if version != SCHEMA_VERSION:
        if isinstance(version, int) and not isinstance(version, bool):
            raise IncompatibleSchemaError(
                f"_meta.schema_version: file is schema_version {version}; this "
                f"sdk1 reads schema_version {SCHEMA_VERSION}"
            )
        raise _fail(
            "_meta.schema_version",
            f"expected {SCHEMA_VERSION}, got {version!r}",
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
    _check_inheritance(providers)
    return LimitsTable(
        schema_version=SCHEMA_VERSION,
        sources=sources,
        default=default,
        providers=providers,
        layer=layer,
        default_layer=layer,
        meta=meta,
    )


def _check_inheritance(
    providers: dict[str, ProviderEntry],
    fallback: Mapping[str, ProviderEntry] | None = None,
) -> None:
    """Enforce one-level ``inherit``.

    The target must exist, must not be the provider itself, and must not
    inherit in turn. This rules out every cycle, which the resolver would
    otherwise follow until ``RecursionError``. A target missing from
    ``providers`` may be found in ``fallback`` (the bundled providers, for
    an override file applied over a remote copy that dropped one).
    """
    known: Mapping[str, ProviderEntry] = {**(fallback or {}), **providers}
    for entry in providers.values():
        for override in entry.overrides:
            target = override.inherit
            if target is None:
                continue
            where = f"providers.{entry.key}"
            if target not in known:
                raise _fail(where, f"inherit target '{target}' is not a provider key")
            if target == entry.key:
                raise _fail(where, f"override '{override.pattern}' inherits itself")
            if any(o.inherit for o in known[target].overrides):
                raise _fail(
                    where,
                    f"inherit target '{target}' itself inherits; only one level "
                    "of inheritance is supported",
                )


def _read_json(path: Path) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_limits_bytes(raw: bytes, *, source: TableSource, location: str) -> LimitsTable:
    """Validate a whole limits file given as bytes and record its origin.

    Raises ``LimitsSchemaError`` (``IncompatibleSchemaError`` for a schema
    version this sdk1 does not read) on any contract violation.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise LimitsSchemaError(f"{location}: not valid JSON: {e}") from e
    table = _parse_table(data, layer="shipped")
    origin = TableOrigin(
        source=source,
        location=location,
        schema_version=table.schema_version,
        verified_on=_str_or_none(table.meta.get("verified_on")),
        sha256=hashlib.sha256(raw).hexdigest()[:12],
    )
    return replace(table, origin=origin)


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def load_limits_table(path: str | Path | None = None) -> LimitsTable:
    """Load and validate a limits file (the bundled one by default).

    Raises ``LimitsSchemaError`` on any contract violation; a malformed
    bundled file is a programming error that the test suite catches.
    """
    target = Path(path) if path is not None else BUNDLED_LIMITS_PATH
    try:
        raw = target.read_bytes()
    except OSError as e:
        raise LimitsSchemaError(f"{target}: cannot read limits file: {e}") from e
    return parse_limits_bytes(raw, source="bundled", location=str(target))


def apply_override_file(
    table: LimitsTable, path: str | Path, *, bundled: LimitsTable | None = None
) -> LimitsTable:
    """Apply an override file: whole provider entries, ``default`` per field.

    A provider present in the override replaces the shipped entry wholesale.
    A ``default`` block is merged field by field over the shipped default,
    so an override that sets only ``max_images_per_request`` keeps the
    shipped request-byte and tokens-per-page defaults. Sources are merged so
    an override can cite its own evidence. The override must resolve on its
    own (its ``inherit`` targets may name shipped providers). ``bundled``
    is the bundled table when ``table`` is another copy (remote): an
    ``inherit`` target or source key ``table`` lacks may then name a bundled
    provider or source, and the lookup resolves that parent from the
    bundled entry.
    """
    fallback = {
        key: p
        for key, p in (bundled.providers if bundled is not None else {}).items()
        if key not in table.providers
    }
    try:
        data = _read_json(Path(path))
    except ValueError as e:
        raise LimitsSchemaError(f"{path}: not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise LimitsSchemaError(f"{path}: override must be an object")
    # Check the shapes this function merges before touching them, so a
    # malformed override is a schema error (logged and ignored), never an
    # AttributeError / TypeError that escapes the fallback.
    override_sources = data.get("sources")
    if override_sources is not None and (
        not isinstance(override_sources, dict)
        or not all(isinstance(v, dict) for v in override_sources.values())
    ):
        raise LimitsSchemaError(f"{path}: 'sources' must be an object of objects")
    override_providers = data.get("providers")
    if override_providers is not None and not isinstance(override_providers, dict):
        raise LimitsSchemaError(f"{path}: 'providers' must be an object")
    # Validate the override against the union of sources (the bundled ones
    # too, so a source the remote copy dropped stays citable), and let its
    # inherit targets point at shipped providers.
    known_sources = {**(bundled.sources if bundled is not None else {}), **table.sources}
    merged_sources = {
        k: {"url": v.url, "verified_on": v.verified_on} for k, v in known_sources.items()
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
        for key, p in {**fallback, **table.providers}.items()
        if key not in (candidate.get("providers") or {})
    }
    candidate["providers"] = {**shipped_stubs, **(candidate.get("providers") or {})}
    parsed = _parse_table(candidate, layer="override", require_default=False)

    providers = dict(table.providers)
    for key in data.get("providers") or {}:
        providers[key] = parsed.providers[key]
    # The override may combine with shipped entries into a chain or a cycle
    # (e.g. its anthropic inheriting the shipped openrouter): check the result.
    _check_inheritance(providers, fallback)
    default = {**table.default, **parsed.default}
    for name in DEFAULTABLE_FIELDS:
        if default.get(name) is None or default[name].value is None:
            raise LimitsSchemaError(
                f"{path}: default.{name} must carry a numeric value (it would "
                "remove the shipped default)"
            )
    sources = dict(table.sources)
    sources.update(parsed.sources)
    origin = (
        replace(table.origin, override_file=str(path))
        if table.origin is not None
        else None
    )
    return LimitsTable(
        schema_version=SCHEMA_VERSION,
        sources=sources,
        default=default,
        providers=providers,
        layer="override",
        default_layer=table.default_layer,
        meta=table.meta,
        origin=origin,
        default_override_fields=table.default_override_fields | frozenset(parsed.default),
    )
