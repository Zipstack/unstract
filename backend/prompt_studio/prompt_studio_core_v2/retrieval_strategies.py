"""Retrieval Strategy Metadata for Prompt Studio.

This module contains detailed information about each retrieval strategy
including descriptions, use cases, performance impacts, and technical details.
"""

RETRIEVAL_STRATEGY_METADATA = {
    "simple": {
        "key": "simple",
        "title": "Simple Vector Retrieval",
        "icon": "SearchOutlined",
        "description": (
            "Basic semantic similarity search using vector embeddings with top-k retrieval."
        ),
        "best_for": [
            "Standard document search and Q&A",
            "General knowledge retrieval tasks",
            "Simple semantic similarity matching",
        ],
        "token_usage": "Low (2-5k tokens typical)",
        "cost_impact": "Low ($0.01-0.05 per query)",
        "technical_details": (
            "Uses cosine similarity on document embeddings to find the most relevant chunks. "
            "Simple and efficient for straightforward retrieval tasks."
        ),
    },
    "fusion": {
        "key": "fusion",
        "title": "Fusion Retrieval (RAG Fusion)",
        "icon": "ForkOutlined",
        "description": (
            "Generates multiple query variations and combines results using "
            "Reciprocal Rank Fusion (RRF) for improved relevance."
        ),
        "best_for": [
            "Complex queries requiring comprehensive coverage",
            "Handling ambiguous or multi-faceted questions",
            "Improving recall when simple retrieval misses context",
        ],
        "token_usage": "High (10-25k tokens typical)",
        "cost_impact": "High ($0.15-0.40 per query)",
        "technical_details": (
            "Creates 3-5 query variations using LLM, retrieves results for each, "
            "then applies RRF scoring to merge and rank results. Significantly improves "
            "retrieval quality at higher cost."
        ),
    },
    "subquestion": {
        "key": "subquestion",
        "title": "Sub-Question Retrieval",
        "icon": "QuestionCircleOutlined",
        "description": (
            "Decomposes complex queries into sub-questions and retrieves relevant "
            "context for each before synthesizing the final answer."
        ),
        "best_for": [
            "Multi-part analytical questions",
            "Research queries requiring multiple perspectives",
            "Complex reasoning tasks spanning multiple topics",
        ],
        "token_usage": "High (15-30k tokens typical)",
        "cost_impact": "High ($0.20-0.50 per query)",
        "technical_details": (
            "Uses LlamaIndex SubQuestionQueryEngine to break down complex queries, "
            "retrieve context for each sub-question, then synthesize comprehensive answers."
        ),
    },
    "recursive": {
        "key": "recursive",
        "title": "Recursive Retrieval",
        "icon": "ReloadOutlined",
        "description": (
            "Follows document relationships and references recursively to build "
            "comprehensive context from connected information."
        ),
        "best_for": [
            "Documents with hierarchical structures",
            "Following citation trails and references",
            "Building context from interconnected content",
        ],
        "token_usage": "Very High (20-50k tokens typical)",
        "cost_impact": "Very High ($0.30-0.80 per query)",
        "technical_details": (
            "Uses LlamaIndex RecursiveRetriever with configurable depth limits. "
            "Traverses document relationships to gather comprehensive context, "
            "ideal for structured documents."
        ),
    },
    "router": {
        "key": "router",
        "title": "Router-based Retrieval",
        "icon": "ShareAltOutlined",
        "description": (
            "Intelligently routes queries to different retrieval strategies or "
            "data sources based on query analysis."
        ),
        "best_for": [
            "Multi-domain knowledge bases",
            "Adaptive retrieval strategy selection",
            "Handling diverse query types in single system",
        ],
        "token_usage": "Variable (5-20k tokens typical)",
        "cost_impact": "Variable ($0.08-0.30 per query)",
        "technical_details": (
            "Uses LlamaIndex RouterQueryEngine to analyze queries and route to "
            "appropriate retrievers (vector, keyword, or summary-based) dynamically."
        ),
    },
    "keyword_table": {
        "key": "keyword_table",
        "title": "Keyword Table Retrieval",
        "icon": "TableOutlined",
        "description": (
            "Extracts and indexes keywords from documents, then performs exact "
            "and fuzzy keyword matching for retrieval."
        ),
        "best_for": [
            "Technical documentation with specific terminology",
            "Exact term and phrase matching",
            "Complementing semantic search with keyword precision",
        ],
        "token_usage": "Low (3-8k tokens typical)",
        "cost_impact": "Low ($0.02-0.08 per query)",
        "technical_details": (
            "Uses LlamaIndex SimpleKeywordTableIndex to extract keywords during indexing "
            "and match against query keywords with TF-IDF scoring."
        ),
    },
    "automerging": {
        "key": "automerging",
        "title": "Auto-Merging Retrieval",
        "icon": "MergeCellsOutlined",
        "description": (
            "Automatically merges adjacent and related document chunks to provide "
            "more comprehensive context while avoiding fragmentation."
        ),
        "best_for": [
            "Long-form documents with narrative flow",
            "Maintaining context across chunk boundaries",
            "Reducing information fragmentation",
        ],
        "token_usage": "Medium (8-18k tokens typical)",
        "cost_impact": "Medium ($0.10-0.25 per query)",
        "technical_details": (
            "Uses LlamaIndex AutoMergingRetriever to dynamically merge leaf nodes "
            "with parent nodes when retrieved chunks are related, preserving document coherence."
        ),
    },
}


def get_retrieval_strategy_metadata():
    """Get all retrieval strategy metadata.

    Returns:
        dict: Dictionary containing metadata for all retrieval strategies.
    """
    return RETRIEVAL_STRATEGY_METADATA


def get_retrieval_strategy_choices():
    """Get retrieval strategy choices for select fields.

    Returns:
        list: List of tuples (key, title) for use in Django choice fields.
    """
    return [
        (strategy["key"], strategy["title"])
        for strategy in RETRIEVAL_STRATEGY_METADATA.values()
    ]


def get_retrieval_strategy_by_key(key):
    """Get retrieval strategy metadata by key.

    Args:
        key (str): The strategy key (e.g., 'simple', 'fusion', etc.)

    Returns:
        dict: Strategy metadata or None if not found.
    """
    return RETRIEVAL_STRATEGY_METADATA.get(key)
