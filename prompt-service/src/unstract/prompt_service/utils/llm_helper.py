from llama_index.llms.litellm import LiteLLM as LlamaIndexLiteLLM
from unstract.sdk1.llm import LLM


def get_llama_index_llm(llm: LLM) -> LlamaIndexLiteLLM:
    """Convert SDK1 LLM to a llama-index compatible LiteLLM instance.

    SDK1's LLM wraps litellm directly and doesn't inherit from
    llama_index.core.llms.llm.LLM. This helper bridges the gap by
    extracting the litellm-compatible kwargs and constructing a
    LlamaIndexLiteLLM instance that llama-index components can use.

    Args:
        llm: An SDK1 LLM instance whose ``kwargs`` contain
            litellm-compatible parameters (model, api_key, etc.).

    Returns:
        A llama-index compatible LiteLLM instance.
    """
    kwargs = llm.kwargs.copy()
    model = kwargs.pop("model")
    return LlamaIndexLiteLLM(model=model, **kwargs)
