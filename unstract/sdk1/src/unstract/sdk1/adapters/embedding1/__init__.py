from typing import Any

from unstract.sdk1.adapters.base1 import register_adapters
from unstract.sdk1.adapters.embedding1.azure_openai import AzureOpenAIEmbeddingAdapter
from unstract.sdk1.adapters.embedding1.bedrock import AWSBedrockEmbeddingAdapter
from unstract.sdk1.adapters.embedding1.ollama import OllamaEmbeddingAdapter
from unstract.sdk1.adapters.embedding1.openai import OpenAIEmbeddingAdapter
from unstract.sdk1.adapters.embedding1.vertexai import VertexAIEmbeddingAdapter
from unstract.sdk1.adapters.enums import AdapterTypes

adapters: dict[str, dict[str, Any]] = {}

register_adapters(adapters, AdapterTypes.EMBEDDING.name)

__all__ = ["adapters", "AzureOpenAIEmbeddingAdapter", "AWSBedrockEmbeddingAdapter", "OpenAIEmbeddingAdapter", "VertexAIEmbeddingAdapter", "OllamaEmbeddingAdapter"]
