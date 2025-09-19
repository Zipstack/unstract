"""
Tools module for agentic extraction agents.
Currently implements RAG tool for document retrieval and search.
"""

from .rag_tool import RAGTool

__all__ = [
    "RAGTool",
]