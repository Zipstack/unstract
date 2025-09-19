"""
RAG (Retrieval-Augmented Generation) tool for Autogen agents.
This tool enables agents to search and retrieve relevant information from the document
using the same retrieval techniques as the current prompt service with LlamaIndex integration.
"""

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

# Import Unstract SDK components for RAG functionality
from unstract.sdk.embedding import Embedding
from unstract.sdk.index import Index
from unstract.sdk.vector_db import VectorDB
from unstract.sdk.tool.base import BaseTool

# LlamaIndex components for retrieval strategies
from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.query_engine import SubQuestionQueryEngine, RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.tools import QueryEngineTool

logger = logging.getLogger(__name__)


class RetrievalStrategy(str, Enum):
    """Retrieval strategies matching current prompt service."""
    SIMPLE = "simple"
    SUBQUESTION = "subquestion"
    FUSION = "fusion"
    RECURSIVE = "recursive"
    ROUTER = "router"
    KEYWORD_TABLE = "keyword_table"
    AUTOMERGING = "automerging"


class RAGTool:
    """
    RAG tool for Autogen agents to retrieve relevant document content.
    Integrates with Unstract SDK and uses LlamaIndex retrieval strategies
    matching the current prompt service implementation.
    """

    def __init__(
        self,
        doc_id: str,
        platform_key: Optional[str] = None,
        embedding_instance_id: Optional[str] = None,
        vector_db_instance_id: Optional[str] = None,
        top_k: int = 5,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.SIMPLE,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        """
        Initialize RAG tool with retrieval strategies.

        Args:
            doc_id: Document identifier for retrieval
            platform_key: Platform API key
            embedding_instance_id: Embedding adapter instance ID
            vector_db_instance_id: Vector DB adapter instance ID
            top_k: Number of top results to retrieve
            retrieval_strategy: Retrieval strategy to use
            chunk_size: Chunk size for retrieval (0 = full document)
            chunk_overlap: Chunk overlap for retrieval
        """
        self.doc_id = doc_id
        self.platform_key = platform_key or "default"
        self.embedding_instance_id = embedding_instance_id or "default_embedding"
        self.vector_db_instance_id = vector_db_instance_id or "default_vectordb"
        self.top_k = top_k
        self.retrieval_strategy = retrieval_strategy
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize SDK components
        self._initialize_sdk_components()

        # Initialize LlamaIndex components
        self._initialize_llama_index_retrievers()

    def _initialize_sdk_components(self):
        """Initialize Unstract SDK components for RAG."""
        try:
            # Create base tool for SDK operations
            self.tool = BaseTool(platform_key=self.platform_key)

            # Initialize embedding
            self.embedding = Embedding(
                tool=self.tool,
                adapter_instance_id=self.embedding_instance_id,
            )

            # Initialize vector DB
            self.vector_db = VectorDB(
                tool=self.tool,
                adapter_instance_id=self.vector_db_instance_id,
                embedding=self.embedding,
            )

            # Initialize index for querying
            self.index = Index(
                tool=self.tool,
                run_id=f"rag_session_{self.doc_id}",
                capture_metrics=True,
            )

            logger.info(f"RAG tool initialized for doc_id: {self.doc_id}")

        except Exception as e:
            logger.error(f"Error initializing RAG tool: {str(e)}")
            raise

    def _initialize_llama_index_retrievers(self):
        """Initialize LlamaIndex retriever components."""
        try:
            # Get vector store index from SDK
            self.vector_query_engine = self.vector_db.get_vector_store_index()

            # Create document filter for this specific document
            self.doc_filter = MetadataFilters(
                filters=[ExactMatchFilter(key="doc_id", value=self.doc_id)]
            )

            # Initialize retrievers based on strategy
            self._setup_retriever_strategy()

            logger.info(f"LlamaIndex retrievers initialized with strategy: {self.retrieval_strategy}")

        except Exception as e:
            logger.error(f"Error initializing LlamaIndex retrievers: {str(e)}")
            # Fallback to SDK-only approach if LlamaIndex fails
            self.use_llamaindex = False

    def _setup_retriever_strategy(self):
        """Setup retriever based on selected strategy."""
        if self.retrieval_strategy == RetrievalStrategy.SIMPLE:
            self.retriever = self.vector_query_engine.as_retriever(
                similarity_top_k=self.top_k,
                filters=self.doc_filter
            )

        elif self.retrieval_strategy == RetrievalStrategy.FUSION:
            # Multi-query retriever with fusion
            base_retriever = self.vector_query_engine.as_retriever(
                similarity_top_k=self.top_k,
                filters=self.doc_filter
            )
            self.retriever = QueryFusionRetriever(
                retrievers=[base_retriever],
                similarity_top_k=self.top_k,
                num_queries=4,  # Generate 4 query variations
                mode="reciprocal_rerank",
                use_async=True,
            )

        elif self.retrieval_strategy == RetrievalStrategy.SUBQUESTION:
            # Sub-question query engine
            query_engine = self.vector_query_engine.as_query_engine(
                similarity_top_k=self.top_k,
                filters=self.doc_filter
            )
            self.query_engine = SubQuestionQueryEngine.from_defaults(
                query_engine_tools=[
                    QueryEngineTool.from_defaults(
                        query_engine=query_engine,
                        description=f"Useful for retrieving specific facts about document {self.doc_id}",
                    )
                ]
            )

        elif self.retrieval_strategy == RetrievalStrategy.ROUTER:
            # Router query engine with multiple search strategies
            vector_query_engine = self.vector_query_engine.as_query_engine(
                similarity_top_k=self.top_k,
                filters=self.doc_filter
            )

            # Create multiple query engines for routing
            query_engine_tools = [
                QueryEngineTool.from_defaults(
                    query_engine=vector_query_engine,
                    description="Useful for semantic search and finding related content",
                ),
            ]

            self.query_engine = RouterQueryEngine(
                selector=LLMSingleSelector.from_defaults(),
                query_engine_tools=query_engine_tools,
            )

        else:
            # Default to simple retriever
            self.retriever = self.vector_query_engine.as_retriever(
                similarity_top_k=self.top_k,
                filters=self.doc_filter
            )

    def search(self, query: str, context: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for relevant content using configured retrieval strategy.

        Args:
            query: Search query
            context: Additional context for the search

        Returns:
            List of relevant content chunks in answer_prompt format
        """
        try:
            # Handle chunk_size = 0 case (full document retrieval)
            if self.chunk_size == 0:
                return self._retrieve_full_document()

            # Enhance query with context if provided
            if context:
                enhanced_query = f"{context} {query}"
            else:
                enhanced_query = query

            # Use appropriate retrieval method based on strategy
            if self.retrieval_strategy in [RetrievalStrategy.SUBQUESTION, RetrievalStrategy.ROUTER]:
                results = self._query_with_engine(enhanced_query)
            else:
                results = self._retrieve_with_llamaindex(enhanced_query)

            # Format results consistently
            formatted_results = self._format_search_results(results, query)

            logger.info(f"RAG search completed: {len(formatted_results)} results for query: {query[:50]}...")
            return formatted_results

        except Exception as e:
            logger.error(f"Error in RAG search: {str(e)}")
            # Fallback to SDK search if LlamaIndex fails
            return self._fallback_sdk_search(query, context)

    def _retrieve_with_llamaindex(self, query: str) -> Any:
        """Retrieve using LlamaIndex retriever."""
        if hasattr(self, 'retriever'):
            return self.retriever.retrieve(query)
        else:
            # Fallback to simple retriever
            retriever = self.vector_query_engine.as_retriever(
                similarity_top_k=self.top_k,
                filters=self.doc_filter
            )
            return retriever.retrieve(query)

    def _query_with_engine(self, query: str) -> Any:
        """Query using LlamaIndex query engine."""
        if hasattr(self, 'query_engine'):
            response = self.query_engine.query(query)
            return response.source_nodes if hasattr(response, 'source_nodes') else []
        else:
            return self._retrieve_with_llamaindex(query)

    def _retrieve_full_document(self) -> List[Dict[str, Any]]:
        """Retrieve full document content when chunk_size = 0."""
        try:
            # Use SDK to get all document content
            results = self.index.query_index(
                embedding_instance_id=self.embedding_instance_id,
                vector_db_instance_id=self.vector_db_instance_id,
                doc_id=self.doc_id,
                usage_kwargs={"query": "*", "top_k": 1000},  # Large top_k for full retrieval
            )
            return self._format_search_results(results, "full_document")
        except Exception as e:
            logger.error(f"Error retrieving full document: {str(e)}")
            return []

    def _fallback_sdk_search(self, query: str, context: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fallback to SDK search when LlamaIndex fails."""
        try:
            enhanced_query = f"{context} {query}" if context else query

            results = self.index.query_index(
                embedding_instance_id=self.embedding_instance_id,
                vector_db_instance_id=self.vector_db_instance_id,
                doc_id=self.doc_id,
                usage_kwargs={"query": enhanced_query, "top_k": self.top_k},
            )

            return self._format_search_results(results, query)
        except Exception as e:
            logger.error(f"Error in SDK fallback search: {str(e)}")
            return []

    def _format_search_results(self, results: Any, query: str) -> List[Dict[str, Any]]:
        """
        Format search results to match answer_prompt context format.

        Args:
            results: Raw results from retrieval
            query: Original search query

        Returns:
            Formatted results list matching prompt service format
        """
        formatted_results = []

        try:
            # Handle LlamaIndex node results
            if hasattr(results, '__iter__') and not isinstance(results, str):
                for idx, result in enumerate(results[:self.top_k]):
                    if hasattr(result, 'text') and hasattr(result, 'score'):
                        # LlamaIndex node format
                        formatted_result = {
                            "chunk_id": getattr(result, 'id_', f"chunk_{idx}"),
                            "content": result.text,
                            "score": getattr(result, 'score', 1.0),
                            "metadata": getattr(result, 'metadata', {}),
                            "section": getattr(result, 'metadata', {}).get('section', 'unknown'),
                        }
                        formatted_results.append(formatted_result)
                    elif hasattr(result, 'node'):
                        # Handle nested node structure
                        node = result.node
                        formatted_result = {
                            "chunk_id": getattr(node, 'id_', f"chunk_{idx}"),
                            "content": getattr(node, 'text', str(node)),
                            "score": getattr(result, 'score', 1.0),
                            "metadata": getattr(node, 'metadata', {}),
                            "section": getattr(node, 'metadata', {}).get('section', 'unknown'),
                        }
                        formatted_results.append(formatted_result)
                    elif isinstance(result, dict):
                        # Already formatted result
                        formatted_results.append(result)
                    else:
                        # Generic result
                        formatted_results.append({
                            "chunk_id": f"chunk_{idx}",
                            "content": str(result),
                            "score": 1.0,
                            "metadata": {},
                            "section": "unknown",
                        })

            # Handle SDK results
            elif hasattr(results, 'nodes') and results.nodes:
                for idx, node in enumerate(results.nodes[:self.top_k]):
                    formatted_result = {
                        "chunk_id": getattr(node, 'id_', f"chunk_{idx}"),
                        "content": getattr(node, 'text', str(node)),
                        "score": getattr(node, 'score', 1.0),
                        "metadata": getattr(node, 'metadata', {}),
                        "section": getattr(node, 'metadata', {}).get('section', 'unknown'),
                    }
                    formatted_results.append(formatted_result)

        except Exception as e:
            logger.error(f"Error formatting search results: {str(e)}")

        return formatted_results

    def get_context_for_field(self, field_name: str, field_prompt: str) -> str:
        """
        Get relevant context for a specific field extraction using configured strategy.

        Args:
            field_name: Name of the field to extract
            field_prompt: Prompt/description for the field

        Returns:
            Formatted context string matching answer_prompt format
        """
        # Create field-specific query
        query = f"{field_name}: {field_prompt}"
        results = self.search(query, context=f"extracting {field_name}")

        # Format context like answer_prompt service
        context_parts = []
        for result in results:
            content = result.get("content", "")
            score = result.get("score", 0)
            section = result.get("section", "unknown")

            if content and score > 0.3:  # Lower threshold for field context
                # Add section information if available
                if section != "unknown":
                    context_parts.append(f"[Section: {section}]\n{content}")
                else:
                    context_parts.append(content)

        if context_parts:
            context = "\n\n---------------\n\n".join(context_parts)
            return f"Context:\n---------------\n{context}\n-----------------"
        else:
            return f"No specific context found for {field_name}. Please extract from available document content."

    def verify_extraction(
        self,
        field_name: str,
        extracted_value: str,
        confidence_threshold: float = 0.7
    ) -> Dict[str, Any]:
        """
        Verify an extracted value against the document using RAG.

        Args:
            field_name: Name of the extracted field
            extracted_value: The extracted value to verify
            confidence_threshold: Minimum confidence for verification

        Returns:
            Verification results with evidence
        """
        # Search for content that might contradict or confirm the extraction
        verification_query = f"{field_name} {extracted_value}"
        results = self.search(verification_query, context="verification")

        verification_score = 0.0
        supporting_evidence = []
        contradicting_evidence = []

        for result in results:
            content = result.get("content", "").lower()
            score = result.get("score", 0)

            # Enhanced verification logic
            if extracted_value.lower() in content:
                verification_score += score
                supporting_evidence.append(result)
            elif any(
                keyword in content
                for keyword in ["not", "incorrect", "wrong", "different", "instead", "rather"]
            ):
                contradicting_evidence.append(result)

        is_verified = verification_score >= confidence_threshold

        return {
            "is_verified": is_verified,
            "confidence": min(verification_score, 1.0),
            "supporting_evidence": supporting_evidence,
            "contradicting_evidence": contradicting_evidence,
            "verification_query": verification_query,
            "strategy_used": self.retrieval_strategy.value,
        }

    def get_tool_description(self) -> str:
        """Get description of the RAG tool for agents."""
        return f"""
RAG Tool - Retrieval-Augmented Generation (Strategy: {self.retrieval_strategy.value})
Document ID: {self.doc_id}
Chunk Size: {self.chunk_size or 'default'}
Top-K Results: {self.top_k}

Functions:
- search(query, context=None): Search for relevant content using {self.retrieval_strategy.value} strategy
- get_context_for_field(field_name, field_description): Get formatted context for field extraction
- verify_extraction(field_name, extracted_value): Verify extracted values with evidence

Usage examples:
- search("company financial data"): Find financial information
- get_context_for_field("revenue", "annual revenue amount"): Get context for revenue extraction
- verify_extraction("company_name", "Acme Corp"): Verify if company name is correct

Returns structured results with content, relevance scores, sections, and metadata.
        """.strip()

    def to_autogen_function(self) -> Dict[str, Any]:
        """
        Convert RAG tool to Autogen function format.

        Returns:
            Function definition for Autogen agents
        """
        return {
            "name": "rag_search",
            "description": self.get_tool_description(),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for finding relevant document content",
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context to improve search relevance (optional)",
                    },
                },
                "required": ["query"],
            },
            "function": self.search,
        }