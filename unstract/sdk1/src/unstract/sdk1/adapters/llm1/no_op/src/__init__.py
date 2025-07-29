from unstract.sdk.adapters.llm.no_op.src.no_op_llm import NoOpLLM

metadata = {
    "name": NoOpLLM.__name__,
    "version": "1.0.0",
    "adapter": NoOpLLM,
    "description": "NoOp LLM adapter",
    "is_active": True,
}

__all__ = ["NoOpLLM"]
