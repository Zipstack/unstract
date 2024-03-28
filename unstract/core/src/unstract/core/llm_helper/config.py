from dataclasses import dataclass

from unstract.core.utilities import UnstractUtils


class OpenAIKeys:
    OPENAI_API_KEY = "OPENAI_API_KEY"
    OPENAI_API_BASE = "OPENAI_API_BASE"
    OPENAI_API_VERSION = "OPENAI_API_VERSION"
    OPENAI_API_ENGINE = "OPENAI_API_ENGINE"
    OPENAI_API_MODEL = "OPENAI_API_MODEL"
    OPENAI_API_MODEL_EMBEDDING = "OPENAI_API_MODEL_EMBEDDING"
    OPENAI_API_DEPLOYMENT_EMBEDDING = "OPENAI_API_DEPLOYMENT_EMBEDDING"
    OPENAI_API_TYPE = "OPENAI_API_TYPE"


class OpenAIDefaults:
    OPENAI_API_TYPE = "azure"
    OPENAI_API_BASE = "https://pandora-one.openai.azure.com/"
    OPENAI_API_VERSION = "2023-05-15"


@dataclass
class AzureOpenAIConfig:
    model: str
    deployment_name: str
    engine: str
    api_key: str
    api_version: str
    azure_endpoint: str
    api_type: str

    @classmethod
    def from_env(cls) -> "AzureOpenAIConfig":
        kwargs = {
            "model": UnstractUtils.get_env(
                OpenAIKeys.OPENAI_API_MODEL, raise_err=True
            ),
            "deployment_name": UnstractUtils.get_env(
                OpenAIKeys.OPENAI_API_ENGINE, raise_err=True
            ),
            "engine": UnstractUtils.get_env(
                OpenAIKeys.OPENAI_API_ENGINE, raise_err=True
            ),
            "api_key": UnstractUtils.get_env(
                OpenAIKeys.OPENAI_API_KEY, raise_err=True
            ),
            "api_version": UnstractUtils.get_env(
                OpenAIKeys.OPENAI_API_VERSION,
                default=OpenAIDefaults.OPENAI_API_VERSION,
            ),
            "azure_endpoint": UnstractUtils.get_env(
                OpenAIKeys.OPENAI_API_BASE,
                default=OpenAIDefaults.OPENAI_API_BASE,
            ),
            "api_type": UnstractUtils.get_env(
                OpenAIKeys.OPENAI_API_TYPE,
                default=OpenAIDefaults.OPENAI_API_TYPE,
            ),
        }
        return cls(**kwargs)
