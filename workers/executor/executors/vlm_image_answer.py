"""Bridge for the cloud-only VLM image-answer plugin.

Image output mode (an LLMWhisperer x2text adapter with
``output_mode == "image"``) persists per-page PNGs instead of text, so
answering a prompt against such a document means sending those images to a
vision-capable LLM. That consumer ships only with Unstract Cloud, as the
``vlm-image-answer`` executor plugin.

This OSS bridge owns detection and dispatch (mirroring the
``lookup_enrichment`` bridge, with the opposite error policy — lookups
degrade gracefully, image mode must fail loudly):

- Detects image mode from the profile's x2text adapter configuration. The
  executor payload carries only the adapter *instance id* (no metadata),
  so the config is resolved through the platform service once per
  (execution, adapter) and cached.
- When the plugin is installed, delegates the answer to it. RAG retrieval
  is skipped by the caller — image mode has no text to retrieve.
- When the plugin is absent, raises a structured error rather than letting
  the prompt silently answer against the one-line extraction summary.
"""

import logging
from collections import OrderedDict
from typing import Any

from executor.executors.constants import PromptServiceConstants as PSKeys
from executor.executors.exceptions import VlmImageAnswerError
from executor.executors.file_utils import FileUtils
from executor.executors.plugins.loader import ExecutorPluginLoader

from unstract.sdk1.adapters.x2text.constants import (
    ImageOutputConstants,
    build_page_store_dir,
)
from unstract.sdk1.adapters.x2text.page_image_loader import (
    PageCapExceededError,
    PageImageLoadError,
    PageImageSetIncompleteError,
    PageImageSetTooLargeError,
    PageImagesNotFoundError,
)
from unstract.sdk1.platform import PlatformHelper

logger = logging.getLogger(__name__)

PLUGIN_NAME = "vlm-image-answer"

# Stable machine-readable error codes (prefixed onto error messages so they
# survive the string-only propagation to PS / deployment API responses).
IMAGE_OUTPUT_REQUIRES_CLOUD = "IMAGE_OUTPUT_REQUIRES_CLOUD"
IMAGE_OUTPUT_MISSING = "IMAGE_OUTPUT_MISSING"
IMAGE_PAGE_CAP_EXCEEDED = "IMAGE_PAGE_CAP_EXCEEDED"
IMAGE_PAGES_TOO_LARGE = "IMAGE_PAGES_TOO_LARGE"
IMAGE_OUTPUT_UNSUPPORTED_OPERATION = "IMAGE_OUTPUT_UNSUPPORTED_OPERATION"
VISION_LLM_REQUIRED = "VISION_LLM_REQUIRED"

_LLMWHISPERER_ADAPTER_PREFIX = "llmwhisperer|"

# (scope_id, adapter_instance_id) -> resolved config dict | None, where
# scope_id is the execution id or (for IDE runs, which carry no execution
# id) the run id. Run-scoped on purpose: the cache exists to deduplicate
# the N per-prompt resolutions within ONE run — never to cache across
# runs, where it would pin a stale output mode after an adapter edit.
# Bounded so a long-lived worker never grows it unchecked.
_MODE_CACHE: OrderedDict[tuple[str, str], dict[str, Any] | None] = OrderedDict()
_MODE_CACHE_MAX = 256


def _resolve_image_mode_config(
    shim: Any, adapter_instance_id: str, scope_id: str
) -> dict[str, Any] | None:
    """Return the x2text adapter config when it is in image mode, else None.

    Resolution goes through the platform service (the payload has no
    adapter metadata); results are cached per (scope, adapter). With no
    scope id at all, caching is skipped entirely — a shared ("", adapter)
    entry would serve a stale mode to every later run on this worker.
    """
    cache_key = (scope_id, adapter_instance_id)
    if scope_id and cache_key in _MODE_CACHE:
        _MODE_CACHE.move_to_end(cache_key)
        return _MODE_CACHE[cache_key]

    config = PlatformHelper.get_adapter_config(shim, adapter_instance_id) or {}
    adapter_id = str(config.get("adapter_id", ""))
    adapter_metadata = config.get("adapter_metadata") or {}
    is_image_mode = adapter_id.startswith(_LLMWHISPERER_ADAPTER_PREFIX) and (
        adapter_metadata.get(ImageOutputConstants.OUTPUT_MODE)
        == ImageOutputConstants.IMAGE_MODE
    )

    result = config if is_image_mode else None
    if scope_id:
        _MODE_CACHE[cache_key] = result
        while len(_MODE_CACHE) > _MODE_CACHE_MAX:
            _MODE_CACHE.popitem(last=False)
    return result


def detect_image_mode_config(
    *,
    output: dict[str, Any],
    shim: Any,
    usage_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Detect image mode for one prompt; None means normal text path.

    Fast path: the backend stamps the adapter's ``x2text_output_mode``
    onto the per-prompt payload (it already holds the decrypted adapter
    metadata), so text-mode prompts cost nothing here. The platform-
    service resolution runs only as the fallback for payloads without
    the stamp (e.g. API deployments, older payloads).

    Returns the resolved adapter config for the plugin, or ``{}`` when
    image mode was determined from the stamp alone.
    """
    adapter_instance_id = str(output.get(PSKeys.X2TEXT_ADAPTER) or "")
    if not adapter_instance_id:
        return None

    if PSKeys.X2TEXT_OUTPUT_MODE in output:
        stamped_mode = output.get(PSKeys.X2TEXT_OUTPUT_MODE)
        if stamped_mode == ImageOutputConstants.IMAGE_MODE:
            return {}
        return None

    usage_kwargs = usage_kwargs or {}
    # IDE payloads carry no execution_id — fall back to the run id so the
    # cache stays scoped to one run (see _MODE_CACHE).
    scope_id = str(usage_kwargs.get("execution_id") or usage_kwargs.get("run_id") or "")
    return _resolve_image_mode_config(shim, adapter_instance_id, scope_id)


def run_vlm_image_answer(
    *,
    output: dict[str, Any],
    shim: Any,
    llm: Any,
    extract_file_path: str,
    execution_source: str,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    x2text_config: dict[str, Any],
    usage_kwargs: dict[str, Any] | None = None,
) -> str:
    """Answer an image-mode prompt via the cloud plugin.

    The caller has already detected image mode via
    ``detect_image_mode_config``. ``extract_file_path`` must be the
    extract-file path (never the summarize/source rewrite of it) — the
    pages directory is derived from it via the shared writer/reader
    helper.

    Returns:
        The raw answer string (the caller assigns it in place of the
        RAG/completion answer, so type conversion, lookups, webhooks
        etc. run unchanged).

    Raises:
        VlmImageAnswerError: the cloud plugin is not installed, or the
            vision path failed in a way the user must act on (missing
            images, page cap, non-vision LLM).
    """
    usage_kwargs = usage_kwargs or {}
    prompt_name = output.get(PSKeys.NAME, "")
    plugin_cls = ExecutorPluginLoader.get(PLUGIN_NAME)
    if plugin_cls is None:
        raise VlmImageAnswerError(
            "This document was extracted in image output mode, which is "
            "answered by a vision LLM available only on Unstract Cloud. "
            "Switch the profile's text extractor to a text output mode, "
            "or run this on Unstract Cloud.",
            error_code=IMAGE_OUTPUT_REQUIRES_CLOUD,
        )

    shim.stream_log(f"Answering `{prompt_name}` from page images via vision LLM")
    fs = FileUtils.get_fs_instance(execution_source=execution_source)
    page_store_dir = build_page_store_dir(extract_file_path, extract_file_path)

    try:
        outcome = plugin_cls.run_with_metrics(
            output=output,
            llm=llm,
            fs=fs,
            page_store_dir=page_store_dir,
            x2text_config=x2text_config,
            metadata=metadata,
            shim=shim,
            usage_kwargs=usage_kwargs,
        )
    except (PageImagesNotFoundError, PageImageSetIncompleteError) as e:
        raise VlmImageAnswerError(str(e), error_code=IMAGE_OUTPUT_MISSING) from e
    except PageCapExceededError as e:
        raise VlmImageAnswerError(str(e), error_code=IMAGE_PAGE_CAP_EXCEEDED) from e
    except PageImageSetTooLargeError as e:
        raise VlmImageAnswerError(str(e), error_code=IMAGE_PAGES_TOO_LARGE) from e
    except PageImageLoadError as e:
        raise VlmImageAnswerError(str(e), error_code=IMAGE_OUTPUT_MISSING) from e
    except VlmImageAnswerError:
        raise
    except Exception as e:
        # Plugin-defined hard failures carry a stable error_code attribute
        # (e.g. VISION_LLM_REQUIRED). Anything else propagates untouched —
        # never degrade to the text path.
        plugin_code = getattr(e, "error_code", None)
        if isinstance(plugin_code, str) and plugin_code:
            raise VlmImageAnswerError(str(e), error_code=plugin_code) from e
        raise

    llm_metrics = outcome.get("llm_metrics") if isinstance(outcome, dict) else None
    if llm_metrics:
        metrics.setdefault(prompt_name, {})["vlm_image_answer"] = llm_metrics

    answer = outcome["answer"] if isinstance(outcome, dict) else str(outcome)
    shim.stream_log(f"Vision LLM answered `{prompt_name}`")
    return answer


def raise_if_image_mode_unsupported(
    *,
    operation: str,
    adapter_instance_id: str | None,
    shim: Any,
    scope_id: str = "",
) -> None:
    """Guard operations that cannot run against image-mode documents.

    Single-pass extraction (and any future full-text operation) would
    silently run against the one-line extraction summary — reject it
    explicitly instead.
    """
    if not adapter_instance_id:
        return
    config = _resolve_image_mode_config(shim, str(adapter_instance_id), scope_id)
    if config is not None:
        raise VlmImageAnswerError(
            f"{operation} is not supported in image output mode. Run "
            "prompts individually, or switch the profile's text extractor "
            "to a text output mode.",
            error_code=IMAGE_OUTPUT_UNSUPPORTED_OPERATION,
        )
