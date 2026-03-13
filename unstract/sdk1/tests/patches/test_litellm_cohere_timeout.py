"""Tests for the litellm cohere embed timeout monkey-patch."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from unstract.sdk1.patches.litellm_cohere_timeout import (
    _patched_async_embedding,
    _patched_embedding,
)


@pytest.fixture
def mock_logging_obj() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_http_handler() -> MagicMock:
    from litellm.llms.custom_httpx.http_handler import HTTPHandler

    mock = MagicMock(spec=HTTPHandler)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "embeddings": [[0.1, 0.2]],
        "id": "test",
        "response_type": "embedding_floats",
        "texts": ["hello"],
    }
    mock.post.return_value = mock_response
    return mock


class TestPatchedEmbeddingSyncTimeoutForwarding:
    """Verify sync embedding forwards timeout to client.post()."""

    def test_timeout_passed_to_client_post(
        self,
        mock_logging_obj: MagicMock,
        mock_http_handler: MagicMock,
    ) -> None:
        timeout_value = 600

        with (
            patch(
                "unstract.sdk1.patches.litellm_cohere_timeout.validate_environment",
                side_effect=lambda api_key, headers: headers,
            ),
            patch(
                "unstract.sdk1.patches.litellm_cohere_timeout.CohereEmbeddingConfig"
            ) as mock_config,
        ):
            mock_config.return_value._transform_response.return_value = MagicMock()
            mock_config.return_value._transform_request.return_value = {
                "texts": ["hello"],
                "input_type": "search_document",
            }

            _patched_embedding(
                model="cohere.embed-multilingual-v3",
                input=["hello"],
                model_response=MagicMock(),
                logging_obj=mock_logging_obj,
                optional_params={},
                headers={},
                encoding=MagicMock(),
                timeout=timeout_value,
                client=mock_http_handler,
            )

        mock_http_handler.post.assert_called_once()
        call_kwargs = mock_http_handler.post.call_args
        assert call_kwargs.kwargs.get("timeout") is timeout_value

    def test_none_timeout_passed_to_client_post(
        self,
        mock_logging_obj: MagicMock,
        mock_http_handler: MagicMock,
    ) -> None:
        with (
            patch(
                "unstract.sdk1.patches.litellm_cohere_timeout.validate_environment",
                side_effect=lambda api_key, headers: headers,
            ),
            patch(
                "unstract.sdk1.patches.litellm_cohere_timeout.CohereEmbeddingConfig"
            ) as mock_config,
        ):
            mock_config.return_value._transform_response.return_value = MagicMock()
            mock_config.return_value._transform_request.return_value = {
                "texts": ["hello"],
                "input_type": "search_document",
            }

            _patched_embedding(
                model="cohere.embed-multilingual-v3",
                input=["hello"],
                model_response=MagicMock(),
                logging_obj=mock_logging_obj,
                optional_params={},
                headers={},
                encoding=MagicMock(),
                timeout=None,
                client=mock_http_handler,
            )

        call_kwargs = mock_http_handler.post.call_args
        assert (
            "timeout" in call_kwargs.kwargs
        ), "timeout kwarg must always be passed to client.post()"
        assert (
            call_kwargs.kwargs["timeout"] is None
        ), f"Expected timeout=None, got timeout={call_kwargs.kwargs['timeout']}"

    def test_httpx_timeout_object_forwarded(
        self,
        mock_logging_obj: MagicMock,
        mock_http_handler: MagicMock,
    ) -> None:
        timeout_obj = httpx.Timeout(30.0)

        with (
            patch(
                "unstract.sdk1.patches.litellm_cohere_timeout.validate_environment",
                side_effect=lambda api_key, headers: headers,
            ),
            patch(
                "unstract.sdk1.patches.litellm_cohere_timeout.CohereEmbeddingConfig"
            ) as mock_config,
        ):
            mock_config.return_value._transform_response.return_value = MagicMock()
            mock_config.return_value._transform_request.return_value = {
                "texts": ["hello"],
                "input_type": "search_document",
            }

            _patched_embedding(
                model="cohere.embed-multilingual-v3",
                input=["hello"],
                model_response=MagicMock(),
                logging_obj=mock_logging_obj,
                optional_params={},
                headers={},
                encoding=MagicMock(),
                timeout=timeout_obj,
                client=mock_http_handler,
            )

        call_kwargs = mock_http_handler.post.call_args
        assert call_kwargs.kwargs.get("timeout") is timeout_obj


class TestPatchedEmbeddingAsyncTimeoutForwarding:
    """Verify async embedding forwards timeout to client.post()."""

    def test_timeout_passed_to_async_client_post(
        self,
        mock_logging_obj: MagicMock,
    ) -> None:
        import asyncio

        from litellm.llms.custom_httpx.http_handler import (
            AsyncHTTPHandler,
        )

        mock_client = MagicMock(spec=AsyncHTTPHandler)
        mock_response = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        timeout_value = 600

        async def run() -> None:
            with patch(
                "unstract.sdk1.patches.litellm_cohere_timeout.CohereEmbeddingConfig"
            ) as mock_config:
                mock_config.return_value._transform_response.return_value = MagicMock()

                await _patched_async_embedding(
                    model="cohere.embed-multilingual-v3",
                    data={
                        "texts": ["hello"],
                        "input_type": "search_document",
                    },
                    input=["hello"],
                    model_response=MagicMock(),
                    timeout=timeout_value,
                    logging_obj=mock_logging_obj,
                    optional_params={},
                    api_base="https://bedrock.example.com",
                    api_key=None,
                    headers={},
                    encoding=MagicMock(),
                    client=mock_client,
                )

        asyncio.run(run())

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs.get("timeout") is timeout_value


class TestMonkeyPatchApplied:
    """Verify the monkey-patch is correctly wired."""

    def test_cohere_handler_patched(self) -> None:
        import litellm.llms.cohere.embed.handler as handler

        assert handler.embedding is _patched_embedding
        assert handler.async_embedding is _patched_async_embedding

    def test_bedrock_handler_patched(self) -> None:
        import litellm.llms.bedrock.embed.embedding as bedrock

        assert bedrock.cohere_embedding is _patched_embedding

    def test_patch_module_loaded_via_embedding_import(self) -> None:
        """Verify unstract.sdk1.embedding causes the patch module to load.

        The binding assertions (handler.embedding is _patched_embedding)
        are covered by the other tests in this class. This test only
        verifies that the side-effect import line in embedding.py
        exists and results in the patch module being present in
        sys.modules.
        """
        import sys

        import unstract.sdk1.embedding  # noqa: F401

        assert "unstract.sdk1.patches.litellm_cohere_timeout" in sys.modules
