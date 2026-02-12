from unstract.sdk1.llm import LLM, LLMCompat


def get_llama_index_llm(llm: LLM) -> LLMCompat:
    """Convert SDK1 LLM to a llama-index compatible LLMCompat instance.

    SDK1's LLM wraps litellm directly and doesn't inherit from
    llama_index.core.llms.llm.LLM. This helper bridges the gap by
    constructing an LLMCompat instance that llama-index components
    can use.

    Args:
        llm: An SDK1 LLM instance.

    Returns:
        A llama-index compatible LLMCompat instance.
    """
    return LLMCompat(llm=llm)
