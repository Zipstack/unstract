"""Resolve a provider/model pair to its vision image-request limits.

Provider key = the adapter's ``get_provider()``, with one exception: a
Bedrock model whose validated litellm string starts with ``bedrock_mantle/``
uses ``bedrock_mantle``. The key is never derived from the litellm prefix
alone — MiniMax sends ``anthropic/<id>`` when its api_base ends in
``/anthropic``, NVIDIA Build sends ``custom_openai/<m>`` but has its own
entry, Ollama sends ``ollama_chat/<m>`` under key ``ollama``.

The override-matching rule (candidate order, which override wins,
``inherit``, default fill) is stated once, in this package's README under
"Lookup rules"; ``_candidates`` and ``_match_override`` implement it.

Resolution consults the table only — never ``litellm.model_cost`` — so a
process on the remote cost map and a test on the bundled one resolve the
same validated string identically. ``local_max_input_tokens`` is the one
registry lookup here: an in-process dict read, no per-lookup network call.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import litellm
from unstract.sdk1.utils.image_limits._schema import (
    DEFAULTABLE_FIELDS,
    LIMIT_FIELDS,
    FieldValue,
    Layer,
    LimitsTable,
    OverrideEntry,
    ProviderEntry,
)
from unstract.sdk1.utils.image_limits.source import (
    GUARDED_FIELDS,
    MAX_REMOTE_RAISE_FACTOR,
    REMOTE_SOURCE,
    bundled_table,
    first_clamp_report,
    first_missing_provider_report,
    get_limits_table,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)

BEDROCK_PROVIDER = "bedrock"
BEDROCK_MANTLE_KEY = "bedrock_mantle"
_BEDROCK_MANTLE_PREFIX = "bedrock_mantle/"
PASS_THROUGH_KIND = "pass_through"

# Provider kinds whose default-filled count/byte limits are advisory: a
# pass-through server (vLLM, Ollama, an unknown OpenRouter upstream) has no
# published limit, and a hard default would reject documents it could take.
# Hosted providers keep the default as a conservative hard cap.
PASS_THROUGH_DEFAULTS_ARE_ADVISORY = True


@dataclass(frozen=True)
class LimitValue:
    """One resolved limit with the provenance error messages need."""

    name: str
    value: int | None
    confidence: str  # verified | unverified
    sources: tuple[str, ...]  # source keys
    source_urls: tuple[str, ...]
    verified_on: str | None
    base64_counted: bool
    from_default: bool  # fell through to the top-level default block
    advisory: bool  # warn, do not reject (pass-through provider + default)
    layer: str  # shipped | override
    # True when a remote table asked for more than a data refresh may give
    # and the value was capped from the bundled one (``_clamp_to_bundled``);
    # ``clamped_from`` is what the remote table asked for (None: no limit).
    clamped: bool = False
    clamped_from: int | None = None


@dataclass(frozen=True)
class ImageRequestLimits:
    """Limits for sending page images to one LLM in one request."""

    provider_key: str
    provider_label: str
    provider_kind: str
    model: str  # bare model name used for matching
    matched_override: str | None
    inherited_from: str | None
    is_default_provider: bool
    max_images_per_request: LimitValue
    max_request_bytes: LimitValue
    max_image_bytes: LimitValue
    max_image_px: LimitValue
    many_images_threshold: LimitValue
    many_images_max_px: LimitValue
    max_image_patches: LimitValue
    tokens_per_image: LimitValue
    max_input_tokens: LimitValue
    # Which table answered: e.g. "2026-10-09 remote 1a2b3c4d5e6f".
    table_version: str = ""

    def field(self, name: str) -> LimitValue:
        return getattr(self, name)


def provider_key(adapter_provider: str, validated_model: str) -> str:
    """Table key for an adapter provider and the model string it validated to."""
    if adapter_provider == BEDROCK_PROVIDER and validated_model.startswith(
        _BEDROCK_MANTLE_PREFIX
    ):
        return BEDROCK_MANTLE_KEY
    return adapter_provider


def strip_provider_prefix(model: str) -> str:
    """``azure/my-dep`` -> ``my-dep``; ids without a prefix pass through."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def _empty(name: str) -> FieldValue:
    return FieldValue(
        name=name, value=None, confidence="unverified", sources=(), base64_counted=True
    )


def _materialise(
    table: LimitsTable,
    field_value: FieldValue,
    *,
    from_default: bool,
    advisory: bool,
    layer: str,
) -> LimitValue:
    urls = tuple(table.sources[k].url for k in field_value.sources if k in table.sources)
    dates = [
        table.sources[k].verified_on
        for k in field_value.sources
        if k in table.sources and table.sources[k].verified_on
    ]
    return LimitValue(
        name=field_value.name,
        value=field_value.value,
        confidence=field_value.confidence,
        sources=field_value.sources,
        source_urls=urls,
        verified_on=max(dates) if dates else None,
        base64_counted=field_value.base64_counted,
        from_default=from_default,
        advisory=advisory,
        layer=layer,
    )


def _candidates(
    model: str, cost_model: str | None, extra_model_ids: Sequence[str]
) -> list[str]:
    seen: list[str] = []
    for raw in (cost_model, model, *extra_model_ids):
        if not raw:
            continue
        bare = strip_provider_prefix(raw)
        if bare and bare not in seen:
            seen.append(bare)
    return seen


def _match_override(
    provider: ProviderEntry, candidates: Sequence[str]
) -> tuple[OverrideEntry | None, str | None]:
    for override in provider.overrides:
        for candidate in candidates:
            if override.regex.search(candidate):
                return override, candidate
    return None, None


def _resolve_fields(
    table: LimitsTable,
    provider: ProviderEntry,
    candidates: Sequence[str],
    _seen: frozenset[str] = frozenset(),
) -> tuple[dict[str, FieldValue], dict[str, Layer], str | None, str | None]:
    """Return (fields, field_layers, matched_override_label, inherited_from).

    ``field_layers`` says, per field, which layer's entry supplied it: an
    inherited field comes from the parent provider's entry, the override's
    own fields from this provider's entry. ``_seen`` guards against
    inheritance cycles. The loader already rejects them; this keeps a
    lookup from recursing forever if one slips through.
    """
    fields = dict(provider.defaults)
    layers: dict[str, Layer] = dict.fromkeys(fields, provider.layer)
    override, candidate = _match_override(provider, candidates)
    inherited_from = None
    label = None
    if override is not None:
        label = override.description or override.pattern
        if override.inherit and override.inherit not in (_seen | {provider.key}):
            parent = table.providers.get(override.inherit)
            if parent is None:
                # An override file may inherit from a bundled provider the
                # remote copy dropped (``apply_override_file`` allows it):
                # the parent resolves from the bundled entry, as a missing
                # provider does in ``_resolve_on``.
                _warn_missing(override.inherit, table)
                parent = bundled_table().providers[override.inherit]
            # Match the parent's overrides on what follows the matched slug.
            assert candidate is not None
            match = override.regex.search(candidate)
            remainder = candidate[match.end() :] if match else candidate
            parent_fields, parent_layers, _, _ = _resolve_fields(
                table, parent, [remainder, candidate], _seen | {provider.key}
            )
            fields.update(parent_fields)
            layers.update(parent_layers)
            inherited_from = override.inherit
        fields.update(override.fields)
        layers.update(dict.fromkeys(override.fields, provider.layer))
    return fields, layers, label, inherited_from


def resolve_image_limits(
    adapter_provider: str,
    model: str,
    *,
    cost_model: str | None = None,
    extra_model_ids: Sequence[str] = (),
    table: LimitsTable | None = None,
) -> ImageRequestLimits:
    """Resolve limits for ``model`` (the validated litellm string) on an adapter.

    ``adapter_provider`` is the adapter module's ``get_provider()``.
    ``cost_model`` is the real model id when the routed one is an alias
    (Azure deployment names). ``extra_model_ids`` are extra candidates
    (see the README's "Lookup rules" for how candidates are matched).
    A provider missing from ``table`` but present in the bundled table is
    resolved from the bundled entry, never as pass-through; so is an
    ``inherit`` parent ``table`` lacks (an override file inheriting from a
    provider the remote copy dropped). When ``table``
    is a remote copy, the result is clamped against the bundled table
    (``_clamp_to_bundled``); fields an operator override file set are not.
    """
    table = table or get_limits_table()
    limits = _resolve_on(
        table,
        adapter_provider,
        model,
        cost_model=cost_model,
        extra_model_ids=extra_model_ids,
    )
    if table.origin is None or table.origin.source != REMOTE_SOURCE:
        return limits
    return _clamp_to_bundled(
        limits,
        table,
        adapter_provider,
        model,
        cost_model=cost_model,
        extra_model_ids=extra_model_ids,
    )


def _resolve_on(
    table: LimitsTable,
    adapter_provider: str,
    model: str,
    *,
    cost_model: str | None,
    extra_model_ids: Sequence[str],
) -> ImageRequestLimits:
    """Resolve against ``table`` as written (no clamp)."""
    key = provider_key(adapter_provider, model)
    provider = table.providers.get(key)
    if provider is None:
        shipped = bundled_table()
        if table is not shipped and key in shipped.providers:
            # A provider the bundled table knows never becomes pass-through
            # because another table (remote copy, override) lacks it.
            _warn_missing(key, table)
            return _resolve_on(
                shipped,
                adapter_provider,
                model,
                cost_model=cost_model,
                extra_model_ids=extra_model_ids,
            )
    candidates = _candidates(model, cost_model, extra_model_ids)
    bare_model = strip_provider_prefix(model)

    if provider is None:
        fields: dict[str, FieldValue] = {}
        layers: dict[str, Layer] = {}
        label = None
        inherited_from = None
        layer: Layer = table.default_layer
        kind = PASS_THROUGH_KIND
        display = adapter_provider
    else:
        fields, layers, label, inherited_from = _resolve_fields(
            table, provider, candidates
        )
        layer = provider.layer
        kind = provider.kind
        display = provider.display_name

    advisory_defaults = _defaults_are_advisory(kind)
    resolved: dict[str, LimitValue] = {}
    for name in LIMIT_FIELDS:
        value = fields.get(name)
        if (value is None or value.value is None) and name in DEFAULTABLE_FIELDS:
            default_value = table.default.get(name)
            if default_value is not None and default_value.value is not None:
                resolved[name] = _materialise(
                    table,
                    default_value,
                    from_default=True,
                    advisory=advisory_defaults,
                    layer=table.default_field_layer(name),
                )
                continue
        if value is None:
            value = _empty(name)
        resolved[name] = _materialise(
            table,
            value,
            from_default=False,
            advisory=False,
            layer=layers.get(name, layer),
        )

    return ImageRequestLimits(
        provider_key=key,
        provider_label=display,
        provider_kind=kind,
        model=bare_model,
        matched_override=label,
        inherited_from=inherited_from,
        is_default_provider=provider is None,
        table_version=table.origin.version if table.origin else "",
        **resolved,
    )


def _warn_missing(key: str, table: LimitsTable) -> None:
    """Log, once per provider per process, a fallback to the bundled entry."""
    if not first_missing_provider_report(key):
        return
    logger.warning(
        "Image limits: provider %r is missing from the %s limits table; "
        "using the bundled entry (logged once per process)",
        key,
        table.origin.source if table.origin else "effective",
    )


def _defaults_are_advisory(kind: str) -> bool:
    return PASS_THROUGH_DEFAULTS_ARE_ADVISORY and kind == PASS_THROUGH_KIND


def _with_kind(limit: LimitValue, advisory_defaults: bool) -> LimitValue:
    """``limit`` with the advisory flag a default-filled value has under a kind."""
    if limit.from_default and limit.advisory != advisory_defaults:
        return dataclasses.replace(limit, advisory=advisory_defaults)
    return limit


def _quarter_bytes(limit: LimitValue) -> int | None:
    """An enforced limit scaled to compare exactly across ``base64_counted``.

    Request bytes are compared as raw bytes; a base64-counted limit carries
    3 raw bytes per 4 counted ones. Returning 4x raw keeps it an integer.
    None when nothing is enforced (no value, or advisory only).
    """
    if limit.value is None or limit.advisory:
        return None
    if limit.name == "max_request_bytes" and limit.base64_counted:
        return limit.value * 3
    return limit.value * 4


def _clamp_field(
    remote: LimitValue, shipped: LimitValue, *, key: str, model: str
) -> LimitValue:
    """``min(remote, MAX_REMOTE_RAISE_FACTOR x bundled)``, compared as raw bytes.

    A bundled value that is unknown or advisory leaves the remote value
    alone; a remote value that is not enforced counts as unlimited.
    """
    ceiling = _quarter_bytes(shipped)
    if ceiling is None:
        return remote
    current = _quarter_bytes(remote)
    if current is not None and current <= MAX_REMOTE_RAISE_FACTOR * ceiling:
        return remote
    assert shipped.value is not None  # ceiling is not None
    capped = MAX_REMOTE_RAISE_FACTOR * shipped.value
    _warn_clamp(
        key,
        model,
        remote.name,
        f"remote {_describe_limit(remote)}, bundled {_describe_limit(shipped)}; "
        f"using {capped}",
    )
    return dataclasses.replace(
        shipped,
        value=capped,
        confidence="unverified",
        advisory=False,
        layer="shipped",
        clamped=True,
        clamped_from=None if remote.advisory else remote.value,
    )


def _describe_limit(limit: LimitValue) -> str:
    if limit.value is None:
        return "none"
    text = str(limit.value)
    if limit.name == "max_request_bytes":
        text += " (base64-counted)" if limit.base64_counted else " (raw)"
    if limit.advisory:
        text += " advisory"
    return text


def _warn_clamp(key: str, model: str, name: str, detail: str) -> None:
    if not first_clamp_report((key, model, name)):
        return
    logger.warning(
        "Image limits: the remote limits table loosens %s for %r on %r beyond "
        "what a data refresh may (%s): %s. Fix limits.json on main, or ship "
        "the raise in an sdk1 release.",
        name,
        model,
        key,
        f"kind is locked; count/byte limits at most {MAX_REMOTE_RAISE_FACTOR}x "
        "the bundled value",
        detail,
    )


def _clamp_to_bundled(
    limits: ImageRequestLimits,
    table: LimitsTable,
    adapter_provider: str,
    model: str,
    *,
    cost_model: str | None,
    extra_model_ids: Sequence[str],
) -> ImageRequestLimits:
    """Hold a remote-table result to what a data refresh may change.

    The same inputs are resolved against the bundled table. For a provider
    the bundled table knows: the bundled ``kind`` wins (advisory flags
    follow it), and each guarded field (``GUARDED_FIELDS``) is at most
    ``MAX_REMOTE_RAISE_FACTOR`` times the bundled value. Tightening always
    passes. Fields and provider entries an operator override file supplied
    (layer ``override``) are left as they are. A provider the bundled table
    does not know uses the remote data as-is.
    """
    shipped_table = bundled_table()
    key = limits.provider_key
    entry = table.providers.get(key)
    if entry is None or key not in shipped_table.providers:
        return limits
    shipped = _resolve_on(
        shipped_table,
        adapter_provider,
        model,
        cost_model=cost_model,
        extra_model_ids=extra_model_ids,
    )
    changes: dict[str, object] = {}
    kind = limits.provider_kind
    if entry.layer != "override" and kind != shipped.provider_kind:
        _warn_clamp(
            key,
            limits.model,
            "kind",
            f"remote {kind}, bundled {shipped.provider_kind}; using "
            f"{shipped.provider_kind}",
        )
        kind = shipped.provider_kind
        changes["provider_kind"] = kind
    advisory_defaults = _defaults_are_advisory(kind)
    for name in LIMIT_FIELDS:
        value = _with_kind(limits.field(name), advisory_defaults)
        if name in GUARDED_FIELDS and value.layer != "override":
            # Both sides read under the effective kind, so an operator's
            # kind (override file) is compared like for like.
            ceiling = _with_kind(shipped.field(name), advisory_defaults)
            value = _clamp_field(value, ceiling, key=key, model=limits.model)
        if value != limits.field(name):
            changes[name] = value
    return dataclasses.replace(limits, **changes) if changes else limits


def local_max_input_tokens(model: str, cost_model: str | None = None) -> int | None:
    """``max_input_tokens`` from litellm's in-process registry, or None.

    ``litellm.model_cost`` is the cost map litellm loaded at import: the
    remote one in production, the bundled one when
    ``LITELLM_LOCAL_MODEL_COST_MAP`` is set (tests). Reading it makes no
    network call. Never ``litellm.get_model_info``: it can make network
    calls for self-hosted providers and falls back to a number on failure.
    An unknown context window must stay unknown so the token advisory is
    skipped rather than invented.
    """
    registry = litellm.model_cost
    for raw in (cost_model, model):
        if not raw:
            continue
        for key in (raw, strip_provider_prefix(raw)):
            entry = registry.get(key)
            if entry is None:
                continue
            value = entry.get("max_input_tokens")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
    return None


def resolve_image_limits_for_adapter(
    adapter_id: str, adapter_metadata: Mapping[str, object]
) -> ImageRequestLimits:
    """Resolve limits from an LLM adapter id and its stored metadata.

    Runs the adapter's local ``validate`` to obtain the routed model string
    and ``cost_model`` — no ``LLM`` instance, no provider call; the limits
    table comes from memory (``get_limits_table`` never waits on GitHub).
    Raises ``KeyError`` for an unknown adapter id.
    """
    # Imported lazily: adapters.llm1 pulls in every adapter module.
    from unstract.sdk1.adapters.constants import Common
    from unstract.sdk1.adapters.llm1 import adapters

    module = adapters[adapter_id][Common.MODULE]
    validated = module.validate(dict(adapter_metadata))
    model_id = validated.get("model_id")
    return resolve_image_limits(
        module.get_provider(),
        str(validated["model"]),
        cost_model=validated.get("cost_model"),
        extra_model_ids=[str(model_id)] if model_id else (),
    )
