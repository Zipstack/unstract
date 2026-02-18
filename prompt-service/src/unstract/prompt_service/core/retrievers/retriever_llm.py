from collections.abc import Sequence
from typing import Any

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    ChatResponseAsyncGen,
    ChatResponseGen,
    CompletionResponse,
    CompletionResponseAsyncGen,
    CompletionResponseGen,
    LLMMetadata,
    MessageRole,
)
from llama_index.core.llms.llm import LLM as LlamaIndexBaseLLM  # noqa: N811
from unstract.sdk1.llm import LLM, LLMCompat


class RetrieverLLM(LlamaIndexBaseLLM):
    """Bridges SDK1's LLMCompat with llama-index's LLM for retriever use.

    Llama-index's ``resolve_llm()`` asserts ``isinstance(llm, LLM)``
    where ``LLM`` is ``llama_index.core.llms.llm.LLM``. Since SDK1's
    ``LLMCompat`` is a plain class without llama-index inheritance,
    it fails this check.

    ``RetrieverLLM`` inherits from llama-index's ``LLM`` base class
    (passing the isinstance check) and delegates all LLM calls to an
    internal ``LLMCompat`` instance.
    """

    def __init__(self, llm: LLM, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize with an SDK1 LLM instance."""
        super().__init__(**kwargs)
        self._compat = LLMCompat(
            adapter_id=llm._adapter_id,
            adapter_metadata=llm._adapter_metadata,
            adapter_instance_id=llm._adapter_instance_id,
            tool=llm._tool,
            usage_kwargs=llm._usage_kwargs,
            capture_metrics=llm._capture_metrics,
        )

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            is_chat_model=True,
            model_name=self._compat.get_model_name(),
        )

    # ── Sync ─────────────────────────────────────────────────────────────────

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> ChatResponse:
        result = self._compat.chat(messages, **kwargs)
        return ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT,
                content=result.message.content,
            ),
            raw=result.raw,
        )

    def complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> CompletionResponse:
        result = self._compat.complete(prompt, formatted=formatted, **kwargs)
        return CompletionResponse(text=result.text, raw=result.raw)

    def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> ChatResponseGen:
        raise NotImplementedError("stream_chat is not supported.")

    def stream_complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> CompletionResponseGen:
        raise NotImplementedError("stream_complete is not supported.")

    # ── Async ────────────────────────────────────────────────────────────────

    async def achat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> ChatResponse:
        result = await self._compat.achat(messages, **kwargs)
        return ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT,
                content=result.message.content,
            ),
            raw=result.raw,
        )

    async def acomplete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> CompletionResponse:
        result = await self._compat.acomplete(
            prompt, formatted=formatted, **kwargs
        )
        return CompletionResponse(text=result.text, raw=result.raw)

    async def astream_chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> ChatResponseAsyncGen:
        raise NotImplementedError("astream_chat is not supported.")

    async def astream_complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> CompletionResponseAsyncGen:
        raise NotImplementedError("astream_complete is not supported.")
