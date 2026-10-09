"""Resolve a provider/model pair to its vision image-request limits.

Provider key = the adapter's ``get_provider()``, with one exception: a
Bedrock model whose validated litellm string starts with ``bedrock_mantle/``
uses ``bedrock_mantle``. The key is never derived from the litellm prefix
alone — MiniMax sends ``anthropic/<id>`` when its api_base ends in
``/anthropic``, NVIDIA Build sends ``custom_openai/<m>`` but has its own
entry, Ollama sends ``ollama_chat/<m>`` under key ``ollama``.

Matching strips the litellm prefix from the validated model and tries each
provider override pattern (``re.search``, patterns carry ``(?i)``) against
the bare model, then the bare ``cost_model`` (Azure's real model id), then
any extra ids (Bedrock ``model_id`` behind an inference-profile ARN). First
match wins; its fields replace the provider defaults field by field. An
override with ``inherit`` takes the named provider's resolved limits for the
remainder of the slug and then applies its own explicit fields.

Resolution consults the table only — never ``litellm.model_cost`` — so a
process on the remote cost map and a test on the bundled one resolve the
same validated string identically. ``local_max_input_tokens`` is the one
registry lookup here, and it reads the local map only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import litellm
from unstract.sdk1.utils.image_limits._schema import (
    DEFAULTABLE_FIELDS,
    LIMIT_FIELDS,
    FieldValue,
    LimitsTable,
    OverrideEntry,
    ProviderEntry,
    get_limits_table,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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
    table: LimitsTable, provider: ProviderEntry, candidates: Sequence[str]
) -> tuple[dict[str, FieldValue], str | None, str | None, str]:
    """Return (fields, matched_override_label, inherited_from, layer)."""
    fields = dict(provider.defaults)
    override, candidate = _match_override(provider, candidates)
    inherited_from = None
    label = None
    layer = provider.layer
    if override is not None:
        label = override.description or override.pattern
        if override.inherit:
            parent = table.providers[override.inherit]
            # Match the parent's overrides on what follows the matched slug.
            assert candidate is not None
            match = override.regex.search(candidate)
            remainder = candidate[match.end() :] if match else candidate
            parent_fields, _, _, parent_layer = _resolve_fields(
                table, parent, [remainder, candidate]
            )
            fields.update(parent_fields)
            inherited_from = override.inherit
            layer = parent_layer
        fields.update(override.fields)
    return fields, label, inherited_from, layer


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
    (Azure deployment names). ``extra_model_ids`` are tried last.
    """
    table = table or get_limits_table()
    key = provider_key(adapter_provider, model)
    provider = table.providers.get(key)
    candidates = _candidates(model, cost_model, extra_model_ids)
    bare_model = strip_provider_prefix(model)

    if provider is None:
        fields: dict[str, FieldValue] = {}
        label = None
        inherited_from = None
        layer = table.default_layer
        kind = PASS_THROUGH_KIND
        display = adapter_provider
    else:
        fields, label, inherited_from, layer = _resolve_fields(
            table, provider, candidates
        )
        kind = provider.kind
        display = provider.display_name

    advisory_defaults = PASS_THROUGH_DEFAULTS_ARE_ADVISORY and kind == PASS_THROUGH_KIND
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
                    layer=table.default_layer,
                )
                continue
        if value is None:
            value = _empty(name)
        resolved[name] = _materialise(
            table, value, from_default=False, advisory=False, layer=layer
        )

    return ImageRequestLimits(
        provider_key=key,
        provider_label=display,
        provider_kind=kind,
        model=bare_model,
        matched_override=label,
        inherited_from=inherited_from,
        is_default_provider=provider is None,
        **resolved,
    )


def local_max_input_tokens(model: str, cost_model: str | None = None) -> int | None:
    """``max_input_tokens`` from litellm's LOCAL registry, or None when unknown.

    Never ``litellm.get_model_info``: it can make network calls for
    self-hosted providers and falls back to a number on failure. An unknown
    context window must stay unknown so the token term is skipped, not
    turned into a near-zero page cap.
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
    and ``cost_model`` — no ``LLM`` instance, no network. Raises ``KeyError``
    for an unknown adapter id.
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
