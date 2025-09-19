"""Helper for token calculation using LiteLLM model pricing data."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
import tiktoken

from unstract.sdk.file_storage.impl import FileStorage
from unstract.sdk.file_storage.provider import FileStorageProvider

logger = logging.getLogger(__name__)

MODEL_PRICES_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
MODEL_PRICES_TTL_IN_DAYS = 7
MODEL_PRICES_FILE_PATH = "/tmp/model_prices_and_context.json"


class TokenCalculationHelper:
    """Helper class for calculating tokens and context sizes for LLM models."""

    def __init__(
        self,
        url: str = MODEL_PRICES_URL,
        ttl_days: int = MODEL_PRICES_TTL_IN_DAYS,
        file_path: str = MODEL_PRICES_FILE_PATH,
    ):
        self.ttl_days = ttl_days
        self.url = url
        self.file_path = file_path

        # Use local file storage for caching
        self.file_storage = FileStorage(provider=FileStorageProvider.LOCAL)
        self.model_data = self._get_model_data()

    def get_model_context_window(
        self, model_name: str, provider: str | None = None
    ) -> int | None:
        """Get the context window size for a specific model.

        Args:
            model_name: Name of the model
            provider: Optional provider name to disambiguate models

        Returns:
            Context window size in tokens, or None if not found
        """
        if not self.model_data:
            return None

        # Try exact match first
        if model_name in self.model_data:
            model_info = self.model_data[model_name]
            return model_info.get("max_input_tokens") or model_info.get("max_tokens")

        # Filter models that contain the model name
        filtered_models = {
            k: v for k, v in self.model_data.items() if model_name in k.lower()
        }

        if not filtered_models:
            # Try partial match
            filtered_models = {
                k: v
                for k, v in self.model_data.items()
                if any(part in k.lower() for part in model_name.lower().split("-"))
            }

        # If provider is specified, filter by provider
        if provider and filtered_models:
            for key, model_info in filtered_models.items():
                if provider.lower() in model_info.get("litellm_provider", "").lower():
                    return model_info.get("max_input_tokens") or model_info.get(
                        "max_tokens"
                    )

        # Return the first match if no provider specified
        if filtered_models:
            first_model = next(iter(filtered_models.values()))
            return first_model.get("max_input_tokens") or first_model.get("max_tokens")

        return None

    def count_tokens(self, text: str, model_name: str | None = "gpt-3.5-turbo") -> int:
        """Count tokens in the given text using the appropriate tokenizer.

        Args:
            text: Text to count tokens for
            model_name: Model name to determine the tokenizer

        Returns:
            Number of tokens in the text
        """
        try:
            # Try to get the appropriate encoding for the model
            if "gpt-4" in model_name.lower() or "gpt-3" in model_name.lower():
                encoding_name = "cl100k_base"
            elif "codex" in model_name.lower():
                encoding_name = "p50k_base"
            else:
                # Default to cl100k_base for newer models
                encoding_name = "cl100k_base"

            encoding = tiktoken.get_encoding(encoding_name)
            return len(encoding.encode(text))

        except Exception as e:
            logger.warning(
                f"Error counting tokens with tiktoken: {e}. "
                f"Falling back to approximation."
            )
            # Fallback: approximate 1 token ≈ 4 characters
            return len(text) // 4

    def calculate_optimal_chunk_size(
        self,
        model_name: str,
        provider: str | None = None,
        target_utilization: float = 0.25,
    ) -> int:
        """Calculate optimal chunk size based on model's context window.

        Args:
            model_name: Name of the model
            provider: Optional provider name
            target_utilization: Fraction of context window to use per chunk (default 0.25)

        Returns:
            Optimal chunk size in tokens
        """
        context_window = self.get_model_context_window(model_name, provider)

        if not context_window:
            # Default chunk size if model not found
            logger.warning(
                f"Model {model_name} not found in pricing data. Using default chunk size."
            )
            return 1000

        # Calculate optimal chunk size as a fraction of context window
        optimal_size = int(context_window * target_utilization)

        # Apply reasonable bounds
        min_chunk_size = 500
        max_chunk_size = 8000

        return max(min_chunk_size, min(optimal_size, max_chunk_size))

    def _get_model_data(self) -> dict[str, Any] | None:
        """Get model pricing and context data, using cache if available.

        Returns:
            Dictionary of model data, or None if unavailable
        """
        try:
            # Check if cached file exists and is still valid
            if self.file_storage.exists(self.file_path):
                file_mtime = self.file_storage.modification_time(self.file_path)
                file_expiry_date = file_mtime + timedelta(days=self.ttl_days)
                file_expiry_date_utc = file_expiry_date.replace(tzinfo=UTC)
                now_utc = datetime.now().replace(tzinfo=UTC)

                if now_utc < file_expiry_date_utc:
                    logger.info(f"Reading model data from cache: {self.file_path}")
                    file_contents = self.file_storage.read(
                        self.file_path, mode="r", encoding="utf-8"
                    )
                    return json.loads(file_contents)

            # Fetch fresh data from URL
            return self._fetch_and_save_data()

        except Exception as e:
            logger.error(f"Error getting model data: {e}")
            # Return default model data as fallback
            return self._get_default_model_data()

    def _fetch_and_save_data(self) -> dict[str, Any] | None:
        """Fetch model data from URL and cache it.

        Returns:
            Dictionary of model data, or None if fetch fails
        """
        try:
            logger.info(f"Fetching model data from {self.url}")
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            json_data = response.json()

            # Cache the data
            self.file_storage.write(
                path=self.file_path,
                mode="w",
                encoding="utf-8",
                data=json.dumps(json_data, indent=2),
            )

            logger.info(f"Model data cached successfully at {self.file_path}")
            return json_data

        except Exception as e:
            logger.error(f"Error fetching model data: {e}")
            return self._get_default_model_data()

    def _get_default_model_data(self) -> dict[str, Any]:
        """Get default model data as fallback.

        Returns:
            Dictionary with default model configurations
        """
        return {
            "gpt-4": {"max_tokens": 8192, "litellm_provider": "openai"},
            "gpt-4-32k": {"max_tokens": 32768, "litellm_provider": "openai"},
            "gpt-4-turbo": {"max_tokens": 128000, "litellm_provider": "openai"},
            "gpt-3.5-turbo": {"max_tokens": 4096, "litellm_provider": "openai"},
            "gpt-3.5-turbo-16k": {"max_tokens": 16384, "litellm_provider": "openai"},
            "claude-2": {"max_tokens": 100000, "litellm_provider": "anthropic"},
            "claude-3-opus": {"max_tokens": 200000, "litellm_provider": "anthropic"},
            "claude-3-sonnet": {"max_tokens": 200000, "litellm_provider": "anthropic"},
            "claude-3-haiku": {"max_tokens": 200000, "litellm_provider": "anthropic"},
            "llama-2-7b": {"max_tokens": 4096, "litellm_provider": "together_ai"},
            "llama-2-13b": {"max_tokens": 4096, "litellm_provider": "together_ai"},
            "llama-2-70b": {"max_tokens": 4096, "litellm_provider": "together_ai"},
            "llama-3-8b": {"max_tokens": 8192, "litellm_provider": "together_ai"},
            "llama-3-70b": {"max_tokens": 8192, "litellm_provider": "together_ai"},
            "mistral-7b": {"max_tokens": 8192, "litellm_provider": "together_ai"},
            "mixtral-8x7b": {"max_tokens": 32768, "litellm_provider": "together_ai"},
        }
