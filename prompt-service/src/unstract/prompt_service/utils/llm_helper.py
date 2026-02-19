from unstract.prompt_service.core.retrievers.retriever_llm import RetrieverLLM
from unstract.sdk1.llm import LLM


def get_llama_index_llm(llm: LLM) -> RetrieverLLM:
    """Convert SDK1 LLM to a llama-index compatible RetrieverLLM instance.

    SDK1's LLM wraps litellm directly and doesn't inherit from
    llama_index.core.llms.llm.LLM. This helper bridges the gap by
    constructing a RetrieverLLM instance that inherits from llama-index's
    LLM base class (passing resolve_llm checks) and delegates calls to
    SDK1's LLMCompat internally.

    Args:
        llm: An SDK1 LLM instance.

    Returns:
        A llama-index compatible RetrieverLLM instance.
    """
    return RetrieverLLM(llm=llm)
