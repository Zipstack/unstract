from unstract.sdk1.adapters.base1 import BaseParameters

class OpenAIParams(BaseParameters):
    """See https://docs.litellm.ai/docs/providers/openai/"""
    id: str = "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"
    api_key: str
    api_base: str
    api_version: Optional[str] = None

class AzureOpenAIParams(LLMParameters):
    """See https://docs.litellm.ai/docs/providers/azure/#completion---using-azure_ad_token-api_base-api_version"""
    id: str = "azureopenai|592d84b9-fe03-4102-a17e-6b391f32850b"
    api_base: str
    api_version: Optional[str] = None
    api_key: str
    temperature: Optional[float] = 1

class VertexAIParams(LLMParameters):
    id: str = "vertexai|78fa17a5-a619-47d4-ac6e-3fc1698fdb55"
    vertex_credentials: str
    vertex_project: str
    safety_settings: List[Dict[str, str]]

class AWSBedrockParams(LLMParameters):
    id: str = "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"
    aws_access_key_id: Optional[str]
    aws_secret_access_key: Optional[str]
    aws_region_name: Optional[str]

class AnthropicParams(LLMParameters):
    id: str = "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203"
    api_key: str

class AnyscaleParams(LLMParameters):
    id: str = "anyscale|adec9815-eabc-4207-9389-79cb89952639"
    api_key: str

class MistralParams(LLMParameters):
    id: str = "mistral|00f766a5-6d6d-47ea-9f6c-ddb1e8a94e82"
    api_key: str

class OllamaParams(LLMParameters):
    id: str = "ollama|4b8bd31a-ce42-48d4-9d69-f29c12e0f276"
    api_base: str