"""Unstract Prompt Helpers.

This package provides decoupled helper functions for prompt processing,
LLM interactions, and document processing that were previously part of
the Prompt Studio service.

The helpers are designed to be:
- Framework agnostic (no Flask/Django dependencies)
- Easily testable in isolation
- Reusable across different services and workflows
- Stateless and side-effect free where possible

Key Modules:
- llm: LLM interaction helpers
- extraction: Text and data extraction utilities  
- chunking: Document chunking and text processing
- embedding: Vector embedding generation
- evaluation: Result evaluation and validation
- formatting: Output formatting and post-processing
- rag: RAG (Retrieval Augmented Generation) helpers
- autogen: Microsoft AutoGen integration utilities

Example Usage:
    from unstract.prompt_helpers.llm import LLMHelper
    from unstract.prompt_helpers.extraction import ExtractionHelper
    
    # Initialize helpers
    llm = LLMHelper(adapter_instance_id="gpt-4")
    extractor = ExtractionHelper()
    
    # Extract text from document
    text = extractor.extract_text_from_file("/path/to/document.pdf")
    
    # Process with LLM
    result = llm.process_prompt("Extract key information from: {text}", {"text": text})
"""

from .llm import LLMHelper
from .extraction import ExtractionHelper, TextExtractionConfig
from .chunking import ChunkingHelper, ChunkingStrategy
from .embedding import EmbeddingHelper
from .evaluation import EvaluationHelper, EvaluationConfig
from .formatting import FormattingHelper
from .rag import RAGHelper, RAGConfig, RAGStrategy
from .models import (
    ProcessingResult,
    ExtractionResult,
    ChunkingResult,
    EmbeddingResult,
    EvaluationResult,
)

# Package metadata
__version__ = "0.1.0"
__author__ = "Unstract Team"
__email__ = "engineering@zipstack.com"
__description__ = "Decoupled prompt processing helper functions"

# Main exports for convenience
__all__ = [
    # Core helpers
    "LLMHelper",
    "ExtractionHelper", 
    "ChunkingHelper",
    "EmbeddingHelper",
    "EvaluationHelper",
    "FormattingHelper",
    "RAGHelper",
    
    # Configuration classes
    "TextExtractionConfig",
    "ChunkingStrategy", 
    "EvaluationConfig",
    "RAGConfig",
    "RAGStrategy",
    
    # Result models
    "ProcessingResult",
    "ExtractionResult",
    "ChunkingResult", 
    "EmbeddingResult",
    "EvaluationResult",
    
    # Package info
    "__version__",
]

# Convenience factory functions
def create_llm_helper(adapter_instance_id: str, **kwargs) -> LLMHelper:
    """Create LLM helper with specified adapter."""
    return LLMHelper(adapter_instance_id=adapter_instance_id, **kwargs)

def create_extraction_helper(**kwargs) -> ExtractionHelper:
    """Create extraction helper with default configuration.""" 
    return ExtractionHelper(**kwargs)

def create_rag_helper(
    llm_adapter_id: str,
    embedding_adapter_id: str,
    vector_db_adapter_id: str,
    **kwargs
) -> RAGHelper:
    """Create RAG helper with specified adapters."""
    return RAGHelper(
        llm_adapter_id=llm_adapter_id,
        embedding_adapter_id=embedding_adapter_id,
        vector_db_adapter_id=vector_db_adapter_id,
        **kwargs
    )