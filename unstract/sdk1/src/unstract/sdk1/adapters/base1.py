import glob
import inspect
import logging
import os
import re
from abc import ABC, abstractmethod
from importlib import import_module
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from typing import Any

from pydantic import BaseModel, Field, model_validator
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.enums import AdapterTypes

logger = logging.getLogger(__name__)

# Anthropic models that have deprecated sampling parameters (`temperature`,
# `top_p`, `top_k`). The patterns are regex-searched against the model id
# after lowercasing and normalizing `.` / `_` to `-`. The match is anchored at
# the trailing edge so that unrelated future ids (`claude-opus-4-70`,
# `claude-opus-4-75`, `claude-opus-4-7verbose`) do not match. A single entry
# covers every encoding of the id we have observed:
#   - Native Anthropic              `claude-opus-4-7`, `anthropic/claude-opus-4-7`
#   - Bedrock foundation model      `anthropic.claude-opus-4-7-<date>-v1:0`
#   - Bedrock cross-region profile  `us.anthropic.claude-opus-4-7-...`,
#                                   `eu.`, `apac.`, `global.` variants
#   - Bedrock foundation-model ARN  `arn:aws:bedrock:<region>::foundation-model/
#                                    anthropic.claude-opus-4-7-...`
#   - Bedrock inference-profile ARN `arn:aws:bedrock:<region>:<account>:
#                                    inference-profile/us.anthropic.claude-opus-4-7-...`
#   - Vertex AI                     `vertex_ai/claude-opus-4-7@<date>`
#   - Azure AI Foundry              deployments whose name embeds `claude-opus-4-7`
# Leading text (route prefixes like `converse/`, `invoke/`, `bedrock/`) passes
# through because the regex is anchored only at the trailing edge.
# Add new entries here when Anthropic deprecates sampling on more models.
# Trailing anchor allows: end-of-string, or one of `-`/`:`/`@`/`/` (the
# delimiters used in date suffixes, ARN paths, Vertex `@<date>`, and the
# `v1:0` tag), or `v` followed by a digit (the version-tag start). A bare
# `v` is intentionally rejected so alpha continuations like `4-7verbose` do
# not silently match.
# See https://docs.claude.com/en/about-claude/models/whats-new-claude-4-7
_SAMPLING_DEPRECATED_MODEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"claude-opus-4-7(?=$|[-:@/]|v\d)"),
)
_DEPRECATED_SAMPLING_PARAMS: tuple[str, ...] = ("temperature", "top_p", "top_k")
# Fields whose value can carry a model id. `model` is universal; `model_id` is
# Bedrock's separate ARN field used for Application Inference Profile cost
# tracking — when callers route through an AIP, the standard model id often
# only appears here, not in `model`.
_MODEL_ID_FIELDS: tuple[str, ...] = ("model", "model_id")
# Substring of a Bedrock Application Inference Profile ARN; the rest of the
# ARN is an opaque profile id so the underlying foundation model id is not
# recoverable from the string. Used only to narrow the debug-breadcrumb path
# on the strip's no-match branch.
_OPAQUE_AIP_ARN_MARKER: str = "application-inference-profile"


def _looks_like_opaque_aip_arn(value: str | None) -> bool:
    """Return True when the value looks like a Bedrock AIP ARN.

    Bedrock AIP ARNs do not carry the underlying foundation-model id in the
    string, so the sampling-strip detector cannot decide whether the call is
    bound for Claude Opus 4.7.
    """
    return bool(value) and _OPAQUE_AIP_ARN_MARKER in value


def _has_deprecated_sampling_params(model: str | None) -> bool:
    """Return True when the model rejects sampling parameters.

    Anthropic deprecated `temperature`, `top_p`, and `top_k` starting with
    Claude Opus 4.7; sending any of them yields a 400 from Anthropic and from
    the providers that proxy it (Bedrock, Azure AI Foundry, Vertex AI).

    The check normalizes case and `.`/`_` separators to `-`, then regex-
    searches against the patterns with a trailing-edge boundary, so
    `claude-opus-4-70` and `claude-opus-4-7verbose` do not match. This
    catches every format that embeds the model id (foundation model ids,
    cross-region profiles, foundation-model ARNs, inference-profile ARNs,
    Vertex `@`-suffixed ids).

    It does NOT catch:
    - Bedrock Application Inference Profile ARNs (e.g.
      `arn:aws:bedrock:...:application-inference-profile/abcd1234`), whose
      tail is an opaque profile id — the underlying model is not recoverable
      from the string. Pass the AIP ARN in `model_id` and keep the standard
      model id in `model`, or the strip won't fire.
    - Azure AI Foundry deployment names that omit the model id; rename the
      deployment to include `claude-opus-4-7` so detection works.
    """
    if not model:
        return False
    normalized = model.lower().replace(".", "-").replace("_", "-")
    return any(rx.search(normalized) for rx in _SAMPLING_DEPRECATED_MODEL_PATTERNS)


def _strip_deprecated_sampling_params(validated: dict[str, "Any"]) -> dict[str, "Any"]:
    """Return a copy of `validated` with deprecated sampling params removed.

    The input dict is not mutated. Returns a shallow copy so callers can rely
    on `before is not after` and follow the file's copy-then-mutate style.

    `temperature` is the load-bearing case: `BaseChatCompletionParameters`
    declares `temperature: float | None = Field(default=0.1)`, so Pydantic's
    `model_dump()` re-emits the default even when the caller never set one.
    `top_p` and `top_k` are not declared fields and are normally dropped by
    Pydantic, but the strip defends against caller-supplied values flowing
    through `**adapter_metadata`.

    Checks both `model` and `model_id` so Bedrock callers routing through an
    Application Inference Profile are covered when the standard model id only
    appears in `model_id`.

    Contract change: the returned dict may not contain a `temperature` key.
    Consumers must read via `.get("temperature")`, not `dict["temperature"]`.
    """
    result = dict(validated)
    if any(_has_deprecated_sampling_params(result.get(f)) for f in _MODEL_ID_FIELDS):
        for param in _DEPRECATED_SAMPLING_PARAMS:
            result.pop(param, None)
    elif any(_looks_like_opaque_aip_arn(result.get(f)) for f in _MODEL_ID_FIELDS):
        # An opaque Bedrock AIP ARN reached us with no Anthropic model id in
        # any field. If the underlying foundation model is Opus 4.7+, the
        # upstream call will 400 on `temperature is deprecated`; this debug
        # log makes the strip-skipped state distinguishable from a
        # never-attempted strip when debugging the resulting 400. The guard
        # is intentionally narrow — the broader "any sampling param present"
        # form fires for every routine call because Pydantic's `model_dump`
        # always re-emits the default `temperature=0.1`.
        logger.debug(
            "Sampling-param strip skipped for opaque Bedrock AIP ARN; no "
            "model id field matched a deprecation pattern. Model ids: %s",
            {f: result.get(f) for f in _MODEL_ID_FIELDS if result.get(f)},
        )
    return result


def register_adapters(adapters: dict[str, dict[str, "Any"]], adapter_type: str) -> None:
    """Register all SDK v1 adapters of given type.

    Args:
        adapters: Dictionary to store registered adapters.
        adapter_type: Type of adapter to register.
    """
    adapter_type = adapter_type.lower()
    adapter_type_ver = adapter_type + "1"  # e.g. embedding1, llm1, etc

    cwd = os.path.dirname(os.path.abspath(__file__))
    adapter_dir = os.path.join(cwd, adapter_type_ver)
    py_files = [
        file
        for file in glob.glob(os.path.join(adapter_dir, "*.py"))
        if not file.startswith("__")
    ]

    for py_file in py_files:
        file_name_w_ext = os.path.basename(py_file)
        file_name, ext = os.path.splitext(file_name_w_ext)
        module_name = f"unstract.sdk1.adapters.{adapter_type_ver}.{file_name}"

        for name, obj in inspect.getmembers(import_module(module_name)):
            if name.startswith("__"):
                continue
            if not name.lower().endswith(f"{adapter_type}adapter"):
                continue
            if not inspect.isclass(obj) or obj.__module__ != module_name:
                continue

            # IMPORTANT!
            #
            # We are introspecting adapter classes to retrieve id and metadata.
            # However their repr is DIFFERENT from their type, because
            # pydantic is involved.
            # e.g. repr - class unstract.sdk1.adapters.llm1.base.OpenAILLMAdapter
            #      type - class pydantic._internal._model_construction.ModelMetaclass
            #
            # This leads to following matrix for various introspection methods:
            #
            # member type                 | hasattr(obj, "<member_name>") | "<member_name>" in obj.__dict__ | "<member_name>" in obj.__annotations__  # noqa: E501
            # ----------------------------|-------------------------------|---------------------------------|---------------------------------------  # noqa: E501
            # method    (e.g. `get_id`)   | True                          | True                            | False  # noqa: E501
            # attribute (e.g. `metadata`) | False                         | False                           | True  # noqa: E501
            if hasattr(obj, Common.ADAPTER_ID_GETTER) and hasattr(
                obj, Common.ADAPTER_METADATA_GETTER
            ):
                adapter_id = getattr(obj, Common.ADAPTER_ID_GETTER)()
                metadata = getattr(obj, Common.ADAPTER_METADATA_GETTER)()

                adapters[adapter_id] = {
                    Common.MODULE: metadata[Common.ADAPTER],
                    Common.METADATA: metadata,
                }


class BaseAdapter(ABC):
    """Adapter base class for compatibility with all SDK v1 providers."""

    @staticmethod
    @abstractmethod
    def get_id() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_name() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_description() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_provider() -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_icon() -> str:
        pass

    @classmethod
    def get_json_schema(cls) -> str:
        schema_path = (
            f"{os.path.dirname(__file__)}/"
            f"{cls.get_adapter_type().name.lower()}1/static/"
            f"{cls.get_provider()}.json"
        )
        with open(schema_path) as f:
            return f.read()

    @staticmethod
    @abstractmethod
    def get_adapter_type() -> AdapterTypes:
        pass


class BaseChatCompletionParameters(BaseModel):
    """Base parameters for all SDK v1 providers.

    See https://docs.litellm.ai/docs/completion/input#input-params-1
    """

    model: str
    # The sampling temperature to be used, between 0 and 2.
    temperature: float | None = Field(default=0.1, ge=0, le=2)
    # The number of chat completion choices to generate for each input message.
    n: int | None = 1
    timeout: float | int | None = 600
    max_tokens: int | None = None
    max_retries: int | None = None

    @staticmethod
    @abstractmethod
    # NOTE: Apply metadata transformations before provider args validation.
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        pass

    @staticmethod
    @abstractmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        pass


class BaseEmbeddingParameters(BaseModel):
    """Base parameters for all SDK v1 embedding providers."""

    model: str
    timeout: float | int | None = 600
    max_retries: int | None = None

    @staticmethod
    @abstractmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        pass

    @staticmethod
    @abstractmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        pass


class OpenAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/openai/."""

    api_key: str
    api_base: str
    api_version: str | None = None
    reasoning_effort: str | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OpenAILLMParameters.validate_model(adapter_metadata)

        # Handle OpenAI reasoning configuration
        enable_reasoning = adapter_metadata.get("enable_reasoning", False)

        # If enable_reasoning is not explicitly provided but reasoning_effort is present,
        # assume reasoning was enabled in a previous validation
        has_reasoning_effort = (
            "reasoning_effort" in adapter_metadata
            and adapter_metadata.get("reasoning_effort") is not None
        )
        if not enable_reasoning and has_reasoning_effort:
            enable_reasoning = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_reasoning:
            reasoning_effort = adapter_metadata.get("reasoning_effort", "medium")
            result_metadata["reasoning_effort"] = reasoning_effort
            result_metadata["temperature"] = 1

        # Create validation metadata excluding control fields
        exclude_fields = {"enable_reasoning"}
        if not enable_reasoning:
            exclude_fields.add("reasoning_effort")

        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = OpenAILLMParameters(**validation_metadata).model_dump()

        # Clean up result based on reasoning state
        if not enable_reasoning and "reasoning_effort" in validated:
            validated.pop("reasoning_effort")
        elif enable_reasoning:
            validated["reasoning_effort"] = result_metadata.get(
                "reasoning_effort", "medium"
            )

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add openai/ prefix if the model doesn't already have it
        if model.startswith(_OPENAI_PROVIDER_PREFIX):
            return model
        else:
            return f"{_OPENAI_PROVIDER_PREFIX}{model}"


# LiteLLM provider prefixes hoisted to module constants so the same literal is
# not duplicated across `OpenAILLMParameters`, `OpenAICompatibleLLMParameters`,
# and the reasoning-model detector below.
_OPENAI_PROVIDER_PREFIX = "openai/"
_CUSTOM_OPENAI_PROVIDER_PREFIX = "custom_openai/"
_OPENAI_REASONING_MODEL_PATTERN = re.compile(r"^(o1|o3|o4|gpt-5)(?:[-/]|$)")


def _is_openai_reasoning_model(model: str) -> bool:
    """Best-effort detection of OpenAI reasoning model names.

    The check is conservative — it matches only OpenAI's known reasoning
    families (o1, o3, o4, gpt-5) after stripping the LiteLLM `custom_openai/`
    prefix and optional `openai/` sub-prefix. Custom gateway model aliases
    that hide a reasoning model behind an unrelated name still need the
    explicit `enable_reasoning` opt-in.
    """
    if not model:
        return False
    if model.startswith(_CUSTOM_OPENAI_PROVIDER_PREFIX):
        model = model[len(_CUSTOM_OPENAI_PROVIDER_PREFIX) :]
    if model.startswith(_OPENAI_PROVIDER_PREFIX):
        model = model[len(_OPENAI_PROVIDER_PREFIX) :]
    return bool(_OPENAI_REASONING_MODEL_PATTERN.match(model.lower()))


def _is_openai_api_endpoint(api_base: str | None) -> bool:
    """Return True when api_base points at OpenAI's own HTTPS API host."""
    if not api_base:
        return False
    parsed = urlparse(api_base)
    return (
        parsed.scheme == "https" and (parsed.hostname or "").lower() == "api.openai.com"
    )


class OpenAICompatibleLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/openai_compatible/."""

    api_key: str | None = None
    api_base: str
    reasoning_effort: str | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OpenAICompatibleLLMParameters.validate_model(
            adapter_metadata
        )
        api_key = adapter_metadata.get("api_key")
        if isinstance(api_key, str) and not api_key.strip():
            adapter_metadata["api_key"] = None

        # Reasoning models (OpenAI gpt-5, o1, o3, ...) routed through an
        # OpenAI-compatible gateway reject `temperature != 1` and `max_tokens`
        # (require `max_completion_tokens`). LiteLLM's `custom_openai` provider
        # is generic and does not apply these transformations, so we route the
        # reasoning-only fields via `extra_body` (which LiteLLM forwards as-is)
        # and strip the rejected fields from the top-level kwargs.
        # Auto-detect known OpenAI reasoning model names so users do not have
        # to know that gpt-5 / o-series need special handling — they can still
        # opt in explicitly for custom gateway aliases that hide the model id.
        enable_reasoning = adapter_metadata.get("enable_reasoning", False)
        has_reasoning_effort = (
            "reasoning_effort" in adapter_metadata
            and adapter_metadata.get("reasoning_effort") is not None
        )
        # When validate() runs again on its own previous output, the reasoning
        # fields live ONLY inside `extra_body` (this method strips them from
        # the top level on the reasoning path). Recover them from there so
        # re-validation is idempotent for non-auto-detected aliases too.
        existing_extra_body = adapter_metadata.get("extra_body")
        has_reasoning_extra_body = (
            isinstance(existing_extra_body, dict)
            and existing_extra_body.get("reasoning_effort") is not None
        )
        # Infer reasoning only when `enable_reasoning` is ABSENT (e.g. on a
        # re-validation pass that already stripped the field). Skip the inference
        # if the user explicitly submitted `enable_reasoning: false` with a
        # leftover `reasoning_effort` — that's an explicit opt-out, not an
        # implicit opt-in.
        if (
            not enable_reasoning
            and "enable_reasoning" not in adapter_metadata
            and (has_reasoning_effort or has_reasoning_extra_body)
        ):
            enable_reasoning = True
        if not enable_reasoning and _is_openai_reasoning_model(adapter_metadata["model"]):
            enable_reasoning = True

        reasoning_effort = (
            adapter_metadata.get("reasoning_effort")
            or (
                existing_extra_body.get("reasoning_effort")
                if isinstance(existing_extra_body, dict)
                else None
            )
            or "medium"
        )

        exclude_fields = {"enable_reasoning"}
        if not enable_reasoning:
            exclude_fields.add("reasoning_effort")
        validation_metadata = {
            k: v for k, v in adapter_metadata.items() if k not in exclude_fields
        }
        validated = OpenAICompatibleLLMParameters(**validation_metadata).model_dump()

        if enable_reasoning:
            # Read max_tokens from the validated dict so Pydantic's `int | None`
            # coercion (e.g. "4096" -> 4096) has already been applied before the
            # value is forwarded to the upstream API via extra_body. On the
            # re-validation path the original max_tokens is in extra_body, not
            # at the top level — fall back to that to keep the value across
            # passes.
            max_tokens = validated.get("max_tokens")
            if max_tokens is None and isinstance(existing_extra_body, dict):
                max_tokens = existing_extra_body.get("max_completion_tokens")
            extra_body = {"reasoning_effort": reasoning_effort}
            if max_tokens is not None:
                extra_body["max_completion_tokens"] = max_tokens
            validated["extra_body"] = extra_body
            validated.pop("temperature", None)
            validated.pop("max_tokens", None)
            validated.pop("reasoning_effort", None)
        else:
            validated.pop("reasoning_effort", None)

        # The custom_openai/ prefix has no entry in the cost price map. Strip
        # it only for OpenAI's own endpoint; other gateways price the same
        # model name differently, so leave their cost unresolved.
        if _is_openai_api_endpoint(validated.get("api_base")):
            validated["cost_model"] = validated["model"][
                len(_CUSTOM_OPENAI_PROVIDER_PREFIX) :
            ]

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = str(adapter_metadata.get("model", "")).strip()
        if not model:
            raise ValueError("model is required for the OpenAI Compatible adapter.")
        if model.startswith(_CUSTOM_OPENAI_PROVIDER_PREFIX):
            return model
        return f"{_CUSTOM_OPENAI_PROVIDER_PREFIX}{model}"


# NVIDIA Build reuses the generic OpenAI Compatible adapter wire protocol with a
# hard-coded endpoint. Cost stays unresolved (LiteLLM prices nothing under the
# generic custom_openai provider, and ships no nvidia_nim prices either).
def _validate_branded_openai_compatible(
    adapter_metadata: dict[str, "Any"], default_api_base: str
) -> dict[str, "Any"]:
    # Endpoint is exposed in the schema with a sane default; honour a user
    # override but fall back to the default when blank/absent (e.g. if the
    # provider ever changes its base URL, users can point at the new one
    # without an adapter release).
    api_base = adapter_metadata.get("api_base")
    if not (isinstance(api_base, str) and api_base.strip()):
        api_base = default_api_base
    adapter_metadata = {**adapter_metadata, "api_base": api_base}
    return OpenAICompatibleLLMParameters.validate(adapter_metadata)


_NVIDIA_BUILD_API_BASE = "https://integrate.api.nvidia.com/v1"
_OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_PROVIDER_PREFIX = "openrouter/"


class NvidiaBuildLLMParameters(OpenAICompatibleLLMParameters):
    """OpenAI-compatible adapter for NVIDIA's hosted models (build.nvidia.com)."""

    # Endpoint defaults to NVIDIA Build; users may override it in the schema.
    # Kept as a required `str` (not widened to None) so a directly-constructed
    # instance is always valid even without going through validate().
    api_base: str = _NVIDIA_BUILD_API_BASE

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        return _validate_branded_openai_compatible(
            adapter_metadata, _NVIDIA_BUILD_API_BASE
        )


class OpenRouterLLMParameters(BaseChatCompletionParameters):
    """Adapter for OpenRouter (openrouter.ai).

    Routed through LiteLLM's native `openrouter/` provider (not the generic
    `custom_openai` path) so that per-token costs resolve for the OpenRouter
    models LiteLLM prices, and reasoning params map natively. LiteLLM's
    openrouter handler applies the provider-specific transforms itself, so the
    `custom_openai` extra_body workaround is intentionally not used here.
    """

    api_key: str
    # Endpoint defaults to OpenRouter; users may override it in the schema.
    api_base: str = _OPENROUTER_API_BASE
    reasoning_effort: str | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata = dict(adapter_metadata)
        api_base = adapter_metadata.get("api_base")
        if not (isinstance(api_base, str) and api_base.strip()):
            adapter_metadata["api_base"] = _OPENROUTER_API_BASE
        adapter_metadata["model"] = OpenRouterLLMParameters.validate_model(
            adapter_metadata
        )
        # Forward reasoning_effort natively only when reasoning is enabled;
        # LiteLLM's openrouter handler maps it to OpenRouter's reasoning param.
        # Drop temperature on the reasoning path — OpenAI o-series models reject
        # a non-default temperature, and OpenRouter forwards it upstream as-is.
        enable_reasoning = adapter_metadata.pop("enable_reasoning", False)
        if enable_reasoning:
            adapter_metadata["temperature"] = None
        else:
            adapter_metadata.pop("reasoning_effort", None)
        return OpenRouterLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = str(adapter_metadata.get("model", "")).strip()
        if not model:
            raise ValueError("model is required for the OpenRouter adapter.")
        if model.startswith(_OPENROUTER_PROVIDER_PREFIX):
            return model
        return f"{_OPENROUTER_PROVIDER_PREFIX}{model}"


class AzureOpenAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/azure/#completion---using-azure_ad_token-api_base-api_version."""

    api_base: str
    api_version: str | None = None
    api_key: str
    temperature: float | None = 1
    num_retries: int | None = 3
    reasoning_effort: str | None = None

    @model_validator(mode="before")
    @classmethod
    def set_model_from_deployment_name(cls, data: dict[str, "Any"]) -> dict[str, "Any"]:
        """Convert deployment_name to model field before validation."""
        if "deployment_name" in data:
            deployment_name = data.pop("deployment_name")
            if not deployment_name.startswith("azure/"):
                deployment_name = f"azure/{deployment_name}"
            data["model"] = deployment_name
        return data

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        # Capture user-provided model name before deployment_name overwrites it
        original_model = adapter_metadata.get("model", "")

        adapter_metadata["model"] = AzureOpenAILLMParameters.validate_model(
            adapter_metadata
        )

        # Ensure we have the endpoint in the right format for Azure
        azure_endpoint = adapter_metadata.get("azure_endpoint", "")
        if azure_endpoint:
            adapter_metadata["api_base"] = azure_endpoint

        # Handle Azure OpenAI reasoning configuration
        enable_reasoning = adapter_metadata.get("enable_reasoning", False)

        # If enable_reasoning is not explicitly provided but reasoning_effort is present,
        # assume reasoning was enabled in a previous validation
        has_reasoning_effort = (
            "reasoning_effort" in adapter_metadata
            and adapter_metadata.get("reasoning_effort") is not None
        )
        if not enable_reasoning and has_reasoning_effort:
            enable_reasoning = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_reasoning:
            reasoning_effort = adapter_metadata.get("reasoning_effort", "medium")
            result_metadata["reasoning_effort"] = reasoning_effort
            result_metadata["temperature"] = 1

        # Create validation metadata excluding control fields
        exclude_fields = {"enable_reasoning"}
        if not enable_reasoning:
            exclude_fields.add("reasoning_effort")

        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = AzureOpenAILLMParameters(**validation_metadata).model_dump()

        # Clean up result based on reasoning state
        if not enable_reasoning and "reasoning_effort" in validated:
            validated.pop("reasoning_effort")
        elif enable_reasoning:
            validated["reasoning_effort"] = result_metadata.get(
                "reasoning_effort", "medium"
            )

        # Preserve actual model name for cost tracking (deployment_name is used
        # for LiteLLM routing but doesn't match pricing table entries)
        if original_model:
            cost_model = original_model
            if not cost_model.startswith("azure/"):
                cost_model = f"azure/{cost_model}"
            validated["cost_model"] = cost_model

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        # deployment_name ALWAYS takes precedence over model
        if "deployment_name" in adapter_metadata:
            deployment_name = adapter_metadata["deployment_name"]
            if deployment_name.startswith("azure/"):
                return deployment_name
            return f"azure/{deployment_name}"

        # Only use model if deployment_name doesn't exist (second validation call)
        model = adapter_metadata.get("model", "")
        if model.startswith("azure/"):
            return model
        return f"azure/{model}"


class VertexAILLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/vertex."""

    vertex_credentials: str
    vertex_project: str
    vertex_location: str | None = None
    safety_settings: list[dict[str, str]]

    @staticmethod
    def _map_vertex_fields(metadata: dict[str, "Any"]) -> None:
        """Map user-facing field names to litellm's vertex_* parameter names."""
        if "json_credentials" in metadata and not metadata.get("vertex_credentials"):
            metadata["vertex_credentials"] = metadata["json_credentials"]
        if "project" in metadata and not metadata.get("vertex_project"):
            metadata["vertex_project"] = metadata["project"]
        loc = metadata.get("location")
        if loc and loc.strip() and not metadata.get("vertex_location"):
            metadata["vertex_location"] = loc.strip()

    @staticmethod
    def _get_thinking_config(
        metadata: dict[str, "Any"], enable_thinking: bool, has_existing: bool
    ) -> dict[str, "Any"] | None:
        """Build thinking configuration for Vertex AI models.

        Returns None if thinking should not be sent (pro models with disabled).
        """
        if enable_thinking:
            if has_existing:
                return metadata["thinking"]
            config = {"type": "enabled"}
            budget = metadata.get("budget_tokens")
            if budget is not None:
                config["budget_tokens"] = budget
            return config

        # Pro models don't allow disabling thinking with budget_tokens=0
        model_name = metadata.get("model", "").lower()
        if "pro" in model_name:
            return None

        # Non-pro models support disabling thinking with budget_tokens=0
        return {"type": "disabled", "budget_tokens": 0}

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        # Make a copy so we don't modify the original
        metadata_copy = {**adapter_metadata}

        # Set model with proper prefix
        metadata_copy["model"] = VertexAILLMParameters.validate_model(metadata_copy)

        # Map user-facing fields to litellm's vertex_* parameter names
        VertexAILLMParameters._map_vertex_fields(metadata_copy)

        # Handle Vertex AI thinking configuration (for Gemini models)
        enable_thinking = metadata_copy.get("enable_thinking", False)

        # If enable_thinking is not explicitly provided but thinking config exists
        has_thinking_config = (
            "thinking" in metadata_copy and metadata_copy.get("thinking") is not None
        )
        if not enable_thinking and has_thinking_config:
            enable_thinking = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = metadata_copy.copy()

        # Get thinking config (may be None for pro models with thinking disabled)
        thinking_config = VertexAILLMParameters._get_thinking_config(
            metadata_copy, enable_thinking, has_thinking_config
        )
        if thinking_config is not None:
            result_metadata["thinking"] = thinking_config
            if enable_thinking and not has_thinking_config:
                result_metadata["temperature"] = 1

        # Handle safety settings
        ss_dict = result_metadata.get("safety_settings", {})

        # Handle case where safety_settings is already a list
        if isinstance(ss_dict, list):
            result_metadata["safety_settings"] = ss_dict
        else:
            # Convert dictionary format to list format
            result_metadata["safety_settings"] = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": ss_dict.get("harassment", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": ss_dict.get("hate_speech", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": ss_dict.get("sexual_content", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": ss_dict.get("dangerous_content", "BLOCK_ONLY_HIGH"),
                },
                {
                    "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
                    "threshold": ss_dict.get("civic_integrity", "BLOCK_ONLY_HIGH"),
                },
            ]

        # These are the fields to preserve (in addition to model fields)
        fields_to_preserve = [
            "max_tokens",
            "max_retries",
            "timeout",
            "temperature",
            "n",
            "stream",
        ]

        # Create validation metadata excluding control fields
        validation_metadata = {
            k: v
            for k, v in result_metadata.items()
            if k not in ("enable_thinking", "budget_tokens", "thinking")
        }

        # First validate using pydantic
        validated_data = VertexAILLMParameters(**validation_metadata).model_dump()

        # Preserve any important fields not in the model
        for field in fields_to_preserve:
            if field in result_metadata and field not in validated_data:
                validated_data[field] = result_metadata[field]

        # Add thinking config only when present (not set for pro models with disabled)
        if "thinking" in result_metadata:
            validated_data["thinking"] = result_metadata["thinking"]

        return _strip_deprecated_sampling_params(validated_data)

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add vertex_ai/ prefix if the model doesn't already have it
        if model.startswith("vertex_ai/"):
            return model
        else:
            return f"vertex_ai/{model}"


# AWS Bedrock auth helpers: shared by LLM and Embedding param classes.
# `auth_type` is a UI-only selector (Access Keys vs IAM Role / Instance
# Profile) that drives form rendering. The backend translates the user's
# choice into actual credential handling here so that both validate()
# methods stay symmetric and a single bug fix applies to both paths.
_BEDROCK_AWS_KEY_FIELDS: tuple[str, ...] = (
    "aws_access_key_id",
    "aws_secret_access_key",
)
# LiteLLM expects the Bedrock bearer token as `api_key`; the UI uses the
# more descriptive `aws_bearer_token` and the resolver translates between them.
_BEDROCK_BEARER_TOKEN_FIELD: str = "aws_bearer_token"
_BEDROCK_LITELLM_BEARER_KWARG: str = "api_key"
_BEDROCK_VALID_AUTH_TYPES: frozenset[str | None] = frozenset(
    {None, "access_keys", "iam_role", "bearer_token"}
)


def _drop_bedrock_access_keys(validated: dict[str, "Any"]) -> None:
    for key in _BEDROCK_AWS_KEY_FIELDS:
        validated.pop(key, None)


def _require_bedrock_access_keys(validated: dict[str, "Any"]) -> None:
    for key in _BEDROCK_AWS_KEY_FIELDS:
        value = validated.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required when auth_type is 'access_keys'.")


def _translate_bedrock_bearer_token(validated: dict[str, "Any"]) -> None:
    """Move ``aws_bearer_token`` to ``api_key``; raise if missing or blank.

    Stripped before storing so surrounding whitespace doesn't reach the
    ``Authorization`` header — AWS rejects mismatched bearer values with
    an opaque 401.
    """
    token = validated.pop(_BEDROCK_BEARER_TOKEN_FIELD, None)
    if not isinstance(token, str) or not token.strip():
        raise ValueError(
            f"{_BEDROCK_BEARER_TOKEN_FIELD} is required when "
            "auth_type is 'bearer_token'."
        )
    validated[_BEDROCK_LITELLM_BEARER_KWARG] = token.strip()


def _resolve_bedrock_aws_credentials(
    adapter_metadata: dict[str, "Any"],
    validated: dict[str, "Any"],
) -> dict[str, "Any"]:
    """Apply auth_type semantics to the validated LiteLLM kwargs.

    Each branch drops the credentials belonging to the *other* modes so a
    re-saved adapter cannot leak stale long-lived secrets. Blank values
    in an explicitly-selected mode raise rather than fall through to the
    boto3 default chain, which would mask the misconfiguration.

    - ``iam_role``: drop access keys and bearer token; boto3's default
      chain (IRSA / instance profile / env vars / AWS Profile) takes over.
    - ``access_keys``: require non-blank access keys; drop bearer token.
    - ``bearer_token``: require non-blank ``aws_bearer_token``; drop
      access keys; translate the token to ``api_key`` for LiteLLM.
    - ``None`` (legacy, pre-``auth_type``): lenient strip of empty access
      keys; drop any bearer token (must be opted into explicitly).

    Raises:
        ValueError: on unknown ``auth_type``, blank access keys in
            ``access_keys`` mode, or blank token in ``bearer_token`` mode.
    """
    auth_type = adapter_metadata.get("auth_type")
    if auth_type not in _BEDROCK_VALID_AUTH_TYPES:
        raise ValueError(
            f"Unknown auth_type {auth_type!r}; expected one of "
            f"{sorted(t for t in _BEDROCK_VALID_AUTH_TYPES if t)!r} or absent."
        )

    if auth_type == "iam_role":
        _drop_bedrock_access_keys(validated)
        validated.pop(_BEDROCK_BEARER_TOKEN_FIELD, None)
        validated.pop(_BEDROCK_LITELLM_BEARER_KWARG, None)
        return validated

    if auth_type == "access_keys":
        _require_bedrock_access_keys(validated)
        validated.pop(_BEDROCK_BEARER_TOKEN_FIELD, None)
        validated.pop(_BEDROCK_LITELLM_BEARER_KWARG, None)
        return validated

    if auth_type == "bearer_token":
        _drop_bedrock_access_keys(validated)
        _translate_bedrock_bearer_token(validated)
        return validated

    # No auth_type: strip blank access keys (boto3 chain takes over) and
    # drop any bearer token — bearer auth must be opted into explicitly
    # via auth_type='bearer_token' rather than promoted from this branch.
    # A non-blank `api_key` is preserved here to support `LLM.complete()`'s
    # re-validation pass, where bearer-mode kwargs round-trip without their
    # original `auth_type`. A blank `api_key` (Pydantic's `None` default
    # for an unset field) is dropped so LiteLLM doesn't see `api_key=None`.
    for key in _BEDROCK_AWS_KEY_FIELDS:
        if not validated.get(key):
            validated.pop(key, None)
    validated.pop(_BEDROCK_BEARER_TOKEN_FIELD, None)
    if not validated.get(_BEDROCK_LITELLM_BEARER_KWARG):
        validated.pop(_BEDROCK_LITELLM_BEARER_KWARG, None)
    return validated


def _pack_bedrock_guardrail_config(metadata: dict[str, "Any"]) -> None:
    """Translate snake_case guardrail_* fields into LiteLLM's guardrailConfig."""
    identifier = _clean_str(metadata.get("guardrail_identifier"))
    if not identifier:
        return
    version = _clean_str(metadata.get("guardrail_version"))
    # Fail fast — Bedrock rejects identifier without version with an opaque error.
    if not version:
        raise ValueError(
            "guardrail_version is required when guardrail_identifier is set."
        )
    cfg: dict[str, str] = {
        "guardrailIdentifier": identifier,
        "guardrailVersion": version,
    }
    trace = _clean_str(metadata.get("guardrail_trace"))
    if trace:
        cfg["trace"] = trace
    metadata["guardrailConfig"] = cfg


def _clean_str(value: str | None) -> str | None:
    """Strip surrounding whitespace; return None if the result is empty."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class AWSBedrockLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/bedrock."""

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    # AWS_BEARER_TOKEN_BEDROCK; resolver translates to LiteLLM's `api_key`.
    aws_bearer_token: str | None = None
    # Declared so it survives `LLM.complete()`'s re-validation of self.kwargs;
    # otherwise Pydantic would drop it as an unknown field.
    api_key: str | None = None
    aws_region_name: str | None = None
    aws_profile_name: str | None = None  # For AWS SSO authentication
    model_id: str | None = None  # For Application Inference Profile (cost tracking)
    max_retries: int | None = None
    # Declared so it survives Pydantic re-validation of kwargs.
    # Matches LiteLLM's Bedrock kwarg name, hence the mixed case.
    guardrailConfig: dict | None = None  # noqa: N815

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AWSBedrockLLMParameters.validate_model(
            adapter_metadata
        )
        if "region_name" in adapter_metadata and not adapter_metadata.get(
            "aws_region_name"
        ):
            adapter_metadata["aws_region_name"] = adapter_metadata["region_name"]

        # Handle AWS Bedrock thinking configuration (for Claude models)
        enable_thinking = adapter_metadata.get("enable_thinking", False)

        # If enable_thinking is not explicitly provided but thinking config is present,
        # assume thinking was enabled in a previous validation
        has_thinking_config = (
            "thinking" in adapter_metadata
            and adapter_metadata.get("thinking") is not None
        )
        if not enable_thinking and has_thinking_config:
            enable_thinking = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_thinking:
            # Set temperature to 1 for thinking mode
            result_metadata["temperature"] = 1

            if has_thinking_config:
                # Preserve existing thinking config
                result_metadata["thinking"] = adapter_metadata["thinking"]
            else:
                # Create new thinking config
                thinking_config = {"type": "enabled"}
                budget_tokens = adapter_metadata.get("budget_tokens")
                if budget_tokens is not None:
                    thinking_config["budget_tokens"] = budget_tokens
                result_metadata["thinking"] = thinking_config
                result_metadata["temperature"] = 1

        _pack_bedrock_guardrail_config(result_metadata)

        # Create validation metadata excluding control fields. `auth_type` is
        # a UI-only selector that drives form rendering; LiteLLM never sees it.
        validation_metadata = {
            k: v
            for k, v in result_metadata.items()
            if k
            not in (
                "enable_thinking",
                "budget_tokens",
                "thinking",
                "auth_type",
                "guardrail_identifier",
                "guardrail_version",
                "guardrail_trace",
            )
        }

        validated = AWSBedrockLLMParameters(**validation_metadata).model_dump()

        # Drop unset value so it isn't forwarded as `None`.
        if not validated.get("guardrailConfig"):
            validated.pop("guardrailConfig", None)

        # Add thinking config to final result if enabled
        if enable_thinking and "thinking" in result_metadata:
            validated["thinking"] = result_metadata["thinking"]

        # Apply Bedrock auth semantics: IAM Role mode drops keys, Access
        # Keys mode requires non-blank values, legacy (no auth_type) is
        # lenient. Reads auth_type from result_metadata since validation_
        # metadata strips it before Pydantic.
        validated = _resolve_bedrock_aws_credentials(result_metadata, validated)
        return _strip_deprecated_sampling_params(validated)

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add bedrock/ prefix if the model doesn't already have it
        if model.startswith("bedrock/"):
            return model
        else:
            return f"bedrock/{model}"


class AnthropicLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/anthropic."""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AnthropicLLMParameters.validate_model(
            adapter_metadata
        )

        # Handle Anthropic thinking configuration
        enable_thinking = adapter_metadata.get("enable_thinking", False)

        # If enable_thinking is not explicitly provided but thinking config is present,
        # assume thinking was enabled in a previous validation
        has_thinking_config = (
            "thinking" in adapter_metadata
            and adapter_metadata.get("thinking") is not None
        )
        if not enable_thinking and has_thinking_config:
            enable_thinking = True

        # Handle extended context (1M tokens) configuration
        enable_extended_context = adapter_metadata.get("enable_extended_context", False)

        # If enable_extended_context is not explicitly provided but extra_headers
        # with context-1m is present, assume it was enabled in a previous validation
        extra_headers = adapter_metadata.get("extra_headers", {}) or {}
        anthropic_beta = str(extra_headers.get("anthropic-beta", ""))
        has_extended_context_header = (
            "extra_headers" in adapter_metadata
            and adapter_metadata.get("extra_headers") is not None
            and "anthropic-beta" in extra_headers
            and "context-1m" in anthropic_beta
        )
        if not enable_extended_context and has_extended_context_header:
            enable_extended_context = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_thinking:
            if has_thinking_config:
                # Preserve existing thinking config
                result_metadata["thinking"] = adapter_metadata["thinking"]
            else:
                # Create new thinking config
                thinking_config = {"type": "enabled"}
                budget_tokens = adapter_metadata.get("budget_tokens")
                if budget_tokens is not None:
                    thinking_config["budget_tokens"] = budget_tokens
                result_metadata["thinking"] = thinking_config
                result_metadata["temperature"] = 1

        # Create validation metadata excluding control fields
        exclude_fields = (
            "enable_thinking",
            "budget_tokens",
            "thinking",
            "enable_extended_context",
            "extra_headers",
        )
        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = AnthropicLLMParameters(**validation_metadata).model_dump()

        # Add thinking config to final result if enabled
        if enable_thinking and "thinking" in result_metadata:
            validated["thinking"] = result_metadata["thinking"]

        # Add extra_headers for extended context (1M tokens) if enabled
        if enable_extended_context:
            validated["extra_headers"] = {"anthropic-beta": "context-1m-2025-08-07"}

        return _strip_deprecated_sampling_params(validated)

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add anthropic/ prefix if the model doesn't already have it
        if model.startswith("anthropic/"):
            return model
        else:
            return f"anthropic/{model}"


class GeminiLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/gemini."""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        result_metadata = adapter_metadata.copy()
        result_metadata["model"] = GeminiLLMParameters.validate_model(adapter_metadata)

        # Handle Gemini thinking configuration
        enable_thinking = adapter_metadata.get("enable_thinking", False)

        # If enable_thinking is not explicitly provided but thinking config is present,
        # assume thinking was enabled in a previous validation
        has_thinking_config = (
            "thinking" in adapter_metadata
            and adapter_metadata.get("thinking") is not None
        )
        if not enable_thinking and has_thinking_config:
            enable_thinking = True

        if enable_thinking:
            if has_thinking_config:
                result_metadata["thinking"] = adapter_metadata["thinking"]
            else:
                budget_tokens = adapter_metadata.get("budget_tokens")
                if budget_tokens is None:
                    raise ValueError(
                        "budget_tokens is required when thinking mode is enabled"
                    )
                if not isinstance(budget_tokens, int) or budget_tokens < 1024:
                    raise ValueError(
                        f"budget_tokens must be an integer >= 1024, got {budget_tokens}"
                    )
                result_metadata["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget_tokens,
                }
            # Gemini thinking mode requires temperature=1
            result_metadata["temperature"] = 1

        # Exclude control fields from pydantic validation
        exclude_fields = ("enable_thinking", "budget_tokens", "thinking")
        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = GeminiLLMParameters(**validation_metadata).model_dump()

        if enable_thinking and "thinking" in result_metadata:
            validated["thinking"] = result_metadata["thinking"]

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = str(adapter_metadata.get("model", "")).strip()
        if not model:
            raise ValueError("model is required")
        if model.startswith("gemini/"):
            return model
        else:
            return f"gemini/{model}"


class AnyscaleLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/anyscale."""

    api_key: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AnyscaleLLMParameters.validate_model(adapter_metadata)

        return AnyscaleLLMParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add anyscale/ prefix if the model doesn't already have it
        if model.startswith("anyscale/"):
            return model
        else:
            return f"anyscale/{model}"


class MistralLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/mistral."""

    api_key: str
    reasoning_effort: str | None = None  # For Magistral models: low, medium, high

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = MistralLLMParameters.validate_model(adapter_metadata)

        # Handle Mistral reasoning configuration (for Magistral models)
        enable_reasoning = adapter_metadata.get("enable_reasoning", False)

        # If enable_reasoning is not explicitly provided but reasoning_effort is present,
        # assume reasoning was enabled in a previous validation
        has_reasoning_effort = (
            "reasoning_effort" in adapter_metadata
            and adapter_metadata.get("reasoning_effort") is not None
        )
        if not enable_reasoning and has_reasoning_effort:
            enable_reasoning = True

        # Create a copy to avoid mutating the original metadata
        result_metadata = adapter_metadata.copy()

        if enable_reasoning:
            reasoning_effort = adapter_metadata.get("reasoning_effort", "medium")
            result_metadata["reasoning_effort"] = reasoning_effort

        # Create validation metadata excluding control fields
        exclude_fields = {"enable_reasoning"}
        if not enable_reasoning:
            exclude_fields.add("reasoning_effort")

        validation_metadata = {
            k: v for k, v in result_metadata.items() if k not in exclude_fields
        }

        validated = MistralLLMParameters(**validation_metadata).model_dump()

        # Clean up result based on reasoning state
        if not enable_reasoning and "reasoning_effort" in validated:
            validated.pop("reasoning_effort")
        elif enable_reasoning:
            validated["reasoning_effort"] = result_metadata.get(
                "reasoning_effort", "medium"
            )

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add mistral/ prefix if the model doesn't already have it
        if model.startswith("mistral/"):
            return model
        else:
            return f"mistral/{model}"


class OllamaLLMParameters(BaseChatCompletionParameters):
    """See https://docs.litellm.ai/docs/providers/ollama."""

    api_base: str
    json_mode: bool | None = False  # Enable JSON mode for structured output

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OllamaLLMParameters.validate_model(adapter_metadata)
        adapter_metadata["api_base"] = adapter_metadata.get(
            "base_url", adapter_metadata.get("api_base", "")
        )

        # Handle JSON mode - convert to response_format
        result_metadata = adapter_metadata.copy()
        json_mode = result_metadata.pop("json_mode", False)

        validated = OllamaLLMParameters(**result_metadata).model_dump()

        # Re-insert response_format after model_dump() since
        # OllamaLLMParameters doesn't declare the field and Pydantic drops it.
        if json_mode:
            validated["response_format"] = {"type": "json_object"}

        return validated

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add ollama_chat/ prefix if the model doesn't already have it
        if model.startswith("ollama_chat/"):
            return model
        else:
            return f"ollama_chat/{model}"


class AzureAIFoundryLLMParameters(BaseChatCompletionParameters):
    """Azure AI Foundry LLM parameters.

    See https://docs.litellm.ai/docs/providers/azure_ai
    """

    api_key: str
    api_base: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AzureAIFoundryLLMParameters.validate_model(
            adapter_metadata
        )

        validated = AzureAIFoundryLLMParameters(**adapter_metadata).model_dump()
        return _strip_deprecated_sampling_params(validated)

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        # Only add azure_ai/ prefix if the model doesn't already have it
        if model.startswith("azure_ai/"):
            return model
        else:
            return f"azure_ai/{model}"


# Embedding Parameter Classes


class OpenAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/openai."""

    api_key: str
    api_base: str | None = None
    embed_batch_size: int | None = 10
    dimensions: int | None = None  # For text-embedding-3-* models
    # LiteLLM sends encoding_format=null when unset; strict OpenAI-compatible
    # endpoints (e.g. NVIDIA Build) reject null, so subclasses default it.
    encoding_format: str | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OpenAIEmbeddingParameters.validate_model(
            adapter_metadata
        )

        return OpenAIEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        return model


# Branded NVIDIA Build embeddings. LiteLLM's generic `custom_openai` provider
# (used by the branded LLM adapters) has no embedding support, so embeddings
# route through LiteLLM's native `nvidia_nim` provider instead, which reuses the
# OpenAI embedding handler. `nvidia_nim` already defaults its api_base to
# `_NVIDIA_BUILD_API_BASE` (https://integrate.api.nvidia.com/v1); we pin the same
# value explicitly so it shows in the schema as an overridable default.
_NVIDIA_NIM_PROVIDER_PREFIX = "nvidia_nim/"


class NvidiaBuildEmbeddingParameters(OpenAIEmbeddingParameters):
    """OpenAI-compatible embeddings via NVIDIA's hosted endpoint (build.nvidia.com)."""

    # Same value LiteLLM's nvidia_nim provider defaults to; users may override it.
    api_base: str = _NVIDIA_BUILD_API_BASE

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata = dict(adapter_metadata)
        # Endpoint is exposed in the schema with a sane default; honour an
        # override but fall back to the default when blank/absent.
        api_base = adapter_metadata.get("api_base")
        if not (isinstance(api_base, str) and api_base.strip()):
            adapter_metadata["api_base"] = _NVIDIA_BUILD_API_BASE
        # NVIDIA rejects the null LiteLLM sends by default; pin a real value.
        adapter_metadata.setdefault("encoding_format", "float")
        adapter_metadata["model"] = NvidiaBuildEmbeddingParameters.validate_model(
            adapter_metadata
        )
        return OpenAIEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = str(adapter_metadata.get("model", "")).strip()
        if not model:
            raise ValueError("model is required for the NVIDIA Build embedding adapter.")
        if model.startswith(_NVIDIA_NIM_PROVIDER_PREFIX):
            return model
        return f"{_NVIDIA_NIM_PROVIDER_PREFIX}{model}"


class OpenAICompatibleEmbeddingParameters(OpenAIEmbeddingParameters):
    """Embeddings for any server implementing the OpenAI embeddings API.

    LiteLLM has no generic `custom_openai` embedding handler, so requests route
    through the `openai/` provider with a user-supplied `api_base` (vLLM,
    self-hosted gateways, third-party providers). Cost stays unresolved since
    the endpoint is arbitrary.
    """

    # api_key is optional (some gateways are keyless); api_base is required.
    api_key: str | None = None
    api_base: str

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata = dict(adapter_metadata)
        api_key = adapter_metadata.get("api_key")
        if isinstance(api_key, str) and not api_key.strip():
            adapter_metadata["api_key"] = None
        # Strict gateways reject the null encoding_format LiteLLM sends by default.
        adapter_metadata.setdefault("encoding_format", "float")
        adapter_metadata["model"] = OpenAICompatibleEmbeddingParameters.validate_model(
            adapter_metadata
        )
        return OpenAICompatibleEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = str(adapter_metadata.get("model", "")).strip()
        if not model:
            raise ValueError(
                "model is required for the OpenAI Compatible embedding adapter."
            )
        if model.startswith(_OPENAI_PROVIDER_PREFIX):
            return model
        return f"{_OPENAI_PROVIDER_PREFIX}{model}"


class AzureOpenAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/azure."""

    api_key: str
    api_base: str
    api_version: str | None
    embed_batch_size: int | None = 5
    num_retries: int | None = 3
    dimensions: int | None = None  # For text-embedding-3-* models

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        # Capture user-provided model name before deployment_name overwrites it
        original_model = adapter_metadata.get("model", "")

        adapter_metadata["model"] = AzureOpenAIEmbeddingParameters.validate_model(
            adapter_metadata
        )

        # Ensure we have the endpoint in the right format for Azure
        azure_endpoint = adapter_metadata.get("azure_endpoint", "")
        if azure_endpoint:
            adapter_metadata["api_base"] = azure_endpoint

        # Map num_retries to max_retries for consistency
        if "num_retries" in adapter_metadata and not adapter_metadata.get("max_retries"):
            adapter_metadata["max_retries"] = adapter_metadata["num_retries"]

        result = AzureOpenAIEmbeddingParameters(**adapter_metadata).model_dump()

        # Preserve actual model name for cost tracking (deployment_name is used
        # for LiteLLM routing but doesn't match pricing table entries)
        if original_model:
            cost_model = original_model
            if not cost_model.startswith("azure/"):
                cost_model = f"azure/{cost_model}"
            result["cost_model"] = cost_model

        return result

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get(
            "deployment_name", ""
        )  # litellm expects model to be in the format of "azure/<deployment_name>"
        # Only add azure/ prefix if the model doesn't already have it
        if model.startswith("azure/"):
            formatted_model = model
        else:
            formatted_model = f"azure/{model}"
        del adapter_metadata["deployment_name"]
        return formatted_model


class VertexAIEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/vertex."""

    vertex_credentials: str
    vertex_project: str
    vertex_location: str | None = None
    embed_batch_size: int | None = 10
    embed_mode: str | None = "default"

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        # Make a copy so we don't modify the original
        metadata_copy = {**adapter_metadata}

        # Set model with proper prefix
        metadata_copy["model"] = VertexAIEmbeddingParameters.validate_model(metadata_copy)

        # Map user-facing fields to litellm's vertex_* parameter names
        VertexAILLMParameters._map_vertex_fields(metadata_copy)

        return VertexAIEmbeddingParameters(**metadata_copy).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class AWSBedrockEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/bedrock."""

    # Region is still mandatory — credentials are the only fields that
    # may be absent (IAM Role / Instance Profile mode).
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    # AWS_BEARER_TOKEN_BEDROCK; resolver translates to LiteLLM's `api_key`.
    aws_bearer_token: str | None = None
    # Declared so it survives Pydantic re-validation if the kwargs ever round-
    # trip through validate() (parity with the LLM param class).
    api_key: str | None = None
    aws_region_name: str | None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = AWSBedrockEmbeddingParameters.validate_model(
            adapter_metadata
        )
        if "region_name" in adapter_metadata and not adapter_metadata.get(
            "aws_region_name"
        ):
            adapter_metadata["aws_region_name"] = adapter_metadata["region_name"]

        # `auth_type` is a UI-only selector; strip before LiteLLM kwargs.
        validation_metadata = {
            k: v for k, v in adapter_metadata.items() if k != "auth_type"
        }

        validated = AWSBedrockEmbeddingParameters(**validation_metadata).model_dump()

        # Apply Bedrock auth semantics: IAM Role drops keys, Access Keys
        # requires non-blank values, legacy (no auth_type) is lenient.
        return _resolve_bedrock_aws_credentials(adapter_metadata, validated)

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model", "")
        return model


class OllamaEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/ollama."""

    api_base: str
    embed_batch_size: int | None = 10

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        adapter_metadata["model"] = OllamaEmbeddingParameters.validate_model(
            adapter_metadata
        )
        adapter_metadata["api_base"] = adapter_metadata.get(
            "base_url", adapter_metadata.get("api_base", "")
        )

        return OllamaEmbeddingParameters(**adapter_metadata).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        model = adapter_metadata.get("model_name", adapter_metadata.get("model", ""))
        if model.startswith("ollama/"):
            return model
        else:
            return f"ollama/{model}"


class GeminiEmbeddingParameters(BaseEmbeddingParameters):
    """See https://docs.litellm.ai/docs/providers/gemini."""

    api_key: str
    embed_batch_size: int | None = None

    @staticmethod
    def validate(adapter_metadata: dict[str, "Any"]) -> dict[str, "Any"]:
        metadata_copy = {**adapter_metadata}
        metadata_copy["model"] = GeminiEmbeddingParameters.validate_model(metadata_copy)

        return GeminiEmbeddingParameters(**metadata_copy).model_dump()

    @staticmethod
    def validate_model(adapter_metadata: dict[str, "Any"]) -> str:
        raw_model = adapter_metadata.get("model")
        model = raw_model.strip() if isinstance(raw_model, str) else ""
        if not model:
            raise ValueError(
                "The 'model' field is required for the Gemini embedding adapter. "
                "Example: 'gemini-embedding-001'"
            )
        if not model.startswith("gemini/"):
            model = f"gemini/{model}"
        return model
