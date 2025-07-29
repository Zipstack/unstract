import logging
import os
import time
from typing import Any

from llama_index.core.llms import LLM

from unstract.sdk.adapters.llm.llm_adapter import LLMAdapter
from unstract.sdk.adapters.llm.no_op.src.no_op_custom_llm import NoOpCustomLLM

logger = logging.getLogger(__name__)


class NoOpLLM(LLMAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("NoOpLlm")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "noOpLlm|f673a5a2-90f9-40f5-94c0-9fbc663b7553"

    @staticmethod
    def get_name() -> str:
        return "No Op LLM"

    @staticmethod
    def get_description() -> str:
        return "No Op LLM"

    @staticmethod
    def get_provider() -> str:
        return "noOpLlm"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/noOpLlm.png"

    def get_llm_instance(self) -> LLM:
        llm: LLM = NoOpCustomLLM(wait_time=self.config.get("wait_time"))
        return llm

    def test_connection(self) -> bool:
        llm = self.get_llm_instance()
        if not llm:
            return False
        llm.complete(
            "The capital of Tamilnadu is ",
            temperature=0.003,
        )
        time.sleep(self.config.get("wait_time"))
        return True
