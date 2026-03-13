"""Monkey-patch for litellm's cohere embed handler timeout bug.

Bug: litellm.llms.cohere.embed.handler.embedding() and async_embedding()
receive a `timeout` parameter but don't forward it to client.post(),
causing "Connection timed out after None seconds" errors.

Affected litellm version: 1.81.7 (also present on latest main as of
2026-03-10).

Activation: This patch is imported as a side-effect from
unstract.sdk1.embedding. Any code path that invokes Bedrock Cohere
embeddings without going through unstract.sdk1.embedding will NOT
have this patch active.

#TODO Remove this patch when litellm ships a fix upstream.
"""

import importlib.metadata
import logging
import warnings

from packaging.version import Version

logger = logging.getLogger(__name__)

# --- Version guard ---
# Only apply the patch on the exact litellm version it was written for.
# Any other version (newer or older) skips the patch with a visible
# warning so engineers know to verify compatibility.
_PATCHED_LITELLM_VERSION = "1.81.7"
_litellm_version = importlib.metadata.version("litellm")
_SKIP_PATCH = Version(_litellm_version) != Version(_PATCHED_LITELLM_VERSION)
if _SKIP_PATCH:
    warnings.warn(
        "litellm_cohere_timeout patch was SKIPPED — not applied. "
        f"Current litellm version: {_litellm_version}. "
        f"Patch was written for: {_PATCHED_LITELLM_VERSION}. "
        "Please verify the upstream fix and remove this module.",
        DeprecationWarning,
        stacklevel=2,
    )
else:
    # Private litellm imports are deferred to here so they are only
    # loaded when the patch will actually be applied.
    import json
    from collections.abc import Callable

    import httpx
    import litellm
    import litellm.llms.bedrock.embed.embedding as _bedrock_embed
    import litellm.llms.cohere.embed.handler as _cohere_handler
    from litellm.litellm_core_utils.litellm_logging import (
        Logging as LiteLLMLoggingObj,
    )
    from litellm.llms.cohere.embed.handler import (
        validate_environment,
    )
    from litellm.llms.cohere.embed.v1_transformation import (
        CohereEmbeddingConfig,
    )
    from litellm.llms.custom_httpx.http_handler import (
        AsyncHTTPHandler,
        HTTPHandler,
        get_async_httpx_client,
    )
    from litellm.types.llms.bedrock import CohereEmbeddingRequest
    from litellm.types.utils import EmbeddingResponse

    _DEFAULT_TIMEOUT = httpx.Timeout(None)

    # Copied from litellm 1.81.7 cohere/embed/handler.py async_embedding().
    # ONLY CHANGE: Added timeout=timeout to the client.post() call.
    # Source: litellm/llms/cohere/embed/handler.py::async_embedding
    async def _patched_async_embedding(  # type: ignore[return]  # noqa: ANN202
        model: str,
        data: dict | CohereEmbeddingRequest,
        input: list,
        model_response: litellm.utils.EmbeddingResponse,
        timeout: float | httpx.Timeout | None,
        logging_obj: LiteLLMLoggingObj,
        optional_params: dict,
        api_base: str,
        api_key: str | None,
        headers: dict,
        encoding: Callable,
        client: AsyncHTTPHandler | None = None,
    ):
        logging_obj.pre_call(
            input=input,
            api_key=api_key,
            additional_args={
                "complete_input_dict": data,
                "headers": headers,
                "api_base": api_base,
            },
        )

        if client is None:
            client = get_async_httpx_client(
                llm_provider=litellm.LlmProviders.COHERE,
                params={"timeout": timeout},
            )

        try:
            response = await client.post(
                api_base,
                headers=headers,
                data=json.dumps(data),
                timeout=timeout,  # ONLY CHANGE: forward timeout to client
            )
        except httpx.HTTPStatusError as e:
            logging_obj.post_call(
                input=input,
                api_key=api_key,
                additional_args={"complete_input_dict": data},
                original_response=e.response.text,
            )
            raise e
        except Exception as e:
            logging_obj.post_call(
                input=input,
                api_key=api_key,
                additional_args={"complete_input_dict": data},
                original_response=str(e),
            )
            raise e

        return CohereEmbeddingConfig()._transform_response(
            response=response,
            api_key=api_key,
            logging_obj=logging_obj,
            data=data,
            model_response=model_response,
            model=model,
            encoding=encoding,
            input=input,
        )

    # Copied from litellm 1.81.7 cohere/embed/handler.py embedding().
    # ONLY CHANGE: Added timeout=timeout to the client.post() call.
    # Source: litellm/llms/cohere/embed/handler.py::embedding
    def _patched_embedding(  # type: ignore[return]  # noqa: ANN202
        model: str,
        input: list,
        model_response: EmbeddingResponse,
        logging_obj: LiteLLMLoggingObj,
        optional_params: dict,
        headers: dict,
        encoding: object,
        data: dict | CohereEmbeddingRequest | None = None,
        complete_api_base: str | None = None,
        api_key: str | None = None,
        aembedding: bool | None = None,
        timeout: float | httpx.Timeout | None = _DEFAULT_TIMEOUT,
        client: HTTPHandler | AsyncHTTPHandler | None = None,
    ):
        headers = validate_environment(api_key, headers=headers)
        embed_url = complete_api_base or "https://api.cohere.ai/v1/embed"

        data = data or CohereEmbeddingConfig()._transform_request(
            model=model, input=input, inference_params=optional_params
        )

        if aembedding is True:
            return _patched_async_embedding(
                model=model,
                data=data,
                input=input,
                model_response=model_response,
                timeout=timeout,
                logging_obj=logging_obj,
                optional_params=optional_params,
                api_base=embed_url,
                api_key=api_key,
                headers=headers,
                encoding=encoding,
                client=(
                    client
                    if client is not None and isinstance(client, AsyncHTTPHandler)
                    else None
                ),
            )

        logging_obj.pre_call(
            input=input,
            api_key=api_key,
            additional_args={"complete_input_dict": data},
        )

        if client is None or not isinstance(client, HTTPHandler):
            client = HTTPHandler(concurrent_limit=1)

        response = client.post(
            embed_url,
            headers=headers,
            data=json.dumps(data),
            timeout=timeout,  # ONLY CHANGE: forward timeout to client
        )

        return CohereEmbeddingConfig()._transform_response(
            response=response,
            api_key=api_key,
            logging_obj=logging_obj,
            data=data,
            model_response=model_response,
            model=model,
            encoding=encoding,
            input=input,
        )

    # Apply the monkey-patch to both the source module and any existing
    # direct bindings (e.g. bedrock's `from ... import embedding as
    # cohere_embedding`), since direct imports capture a reference at
    # import time and won't see module-level replacements.
    _cohere_handler.async_embedding = _patched_async_embedding
    _cohere_handler.embedding = _patched_embedding
    _bedrock_embed.cohere_embedding = _patched_embedding
    logger.info("Applied litellm cohere embed timeout patch")
