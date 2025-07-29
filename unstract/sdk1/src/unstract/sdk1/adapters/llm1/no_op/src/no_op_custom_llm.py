import time
from typing import Any

from llama_index.core.base.llms.types import (
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.core.llms.custom import CustomLLM


class NoOpCustomLLM(CustomLLM):
    wait_time: float

    def __init__(
        self,
        wait_time: float,
    ) -> None:
        wait_time = wait_time
        super().__init__(wait_time=wait_time)

    @classmethod
    def class_name(cls) -> str:
        return "NoOpLLM"

    def _generate_text(self) -> str:
        # Returns a JSON here to support for all enforce types.
        return '{ "response":"This is a sample response from a NoOp LLM Adapter."}'

    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        time.sleep(self.wait_time)
        response_text = self._generate_text()

        return CompletionResponse(
            text=response_text,
        )

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponseGen:

        def gen_response() -> CompletionResponseGen:
            response_text = self._generate_text()
            yield CompletionResponse(
                text=response_text,
                delta=response_text,
            )

        time.sleep(self.wait_time)

        return gen_response()

    @property
    def metadata(self) -> LLMMetadata:
        """Method to fetch LLM metadata. Overriden to extent Base class.

        Returns:
            LLMMetadata
        """
        return LLMMetadata(num_output=-1)
