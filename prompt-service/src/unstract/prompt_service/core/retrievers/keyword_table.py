import logging
import re
from collections import Counter
from typing import Dict, List, Set

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class KeywordTableRetriever(BaseRetriever):
    """Keyword table retrieval class that uses keyword extraction and matching
    for efficient retrieval of relevant documents.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using keyword table technique.
        
        This technique extracts keywords from documents and queries,
        then matches them for efficient retrieval.
        
        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(f"Retrieving chunks for {self.doc_id} using KeywordTableRetriever.")
            
            # Extract keywords from the query
            query_keywords = self._extract_keywords_from_text(self.prompt)
            logger.info(f"Query keywords: {query_keywords}")
            
            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()
            
            # First, do a broad retrieval to get candidate chunks
            base_retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k * 3,  # Get more candidates for keyword filtering
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )
            
            # Get candidate nodes
            candidate_nodes = base_retriever.retrieve(self.prompt)
            
            # Score each node based on keyword matches
            scored_nodes: Dict[str, tuple[str, float]] = {}
            
            for node in candidate_nodes:
                content = node.get_content()
                # Extract keywords from node content
                node_keywords = self._extract_keywords_from_text(content)
                
                # Calculate keyword match score
                keyword_score = self._calculate_keyword_match_score(
                    query_keywords, node_keywords
                )
                
                # Combine with similarity score
                combined_score = (node.score * 0.5) + (keyword_score * 0.5)
                
                if combined_score > 0:
                    scored_nodes[node.node_id] = (content, combined_score)
            
            # Sort by combined score and get top_k
            sorted_nodes = sorted(
                scored_nodes.items(),
                key=lambda x: x[1][1],
                reverse=True
            )[:self.top_k]
            
            # Extract unique text chunks
            chunks: set[str] = {content for _, (content, _) in sorted_nodes}
            
            logger.info(f"Successfully retrieved {len(chunks)} chunks using keyword table.")
            return chunks
            
        except Exception as e:
            logger.error(f"Error during keyword table retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
    
    def _extract_keywords_from_text(self, text: str) -> Set[str]:
        """Extract keywords from text.
        
        Args:
            text: The text to extract keywords from
            
        Returns:
            Set of keywords
        """
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation and split into words
        words = re.findall(r'\b[a-z]+\b', text)
        
        # Remove common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has',
            'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
            'might', 'must', 'shall', 'can', 'cannot', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'them', 'their',
            'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each',
            'every', 'some', 'any', 'few', 'more', 'most', 'other', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off',
            'over', 'under', 'again', 'further', 'then', 'once'
        }
        
        # Filter out stop words and short words
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        # If we have an LLM, use it to extract more sophisticated keywords
        if self.llm and len(' '.join(keywords)) > 100:
            try:
                prompt = f"""Extract the 10 most important keywords from this text:

{text[:500]}...

Provide only the keywords, one per line."""
                
                response = self.llm.complete(prompt)
                if response and response.text:
                    llm_keywords = [
                        keyword.strip().lower()
                        for keyword in response.text.strip().split('\n')
                        if keyword.strip()
                    ]
                    keywords.extend(llm_keywords)
            except Exception as e:
                logger.debug(f"LLM keyword extraction failed: {e}")
        
        # Get most frequent keywords
        keyword_counts = Counter(keywords)
        top_keywords = {word for word, _ in keyword_counts.most_common(20)}
        
        return top_keywords
    
    def _calculate_keyword_match_score(
        self, query_keywords: Set[str], node_keywords: Set[str]
    ) -> float:
        """Calculate a score based on keyword matches.
        
        Args:
            query_keywords: Keywords from the query
            node_keywords: Keywords from the node content
            
        Returns:
            A score between 0 and 1
        """
        if not query_keywords:
            return 0.0
        
        # Calculate intersection
        matches = query_keywords.intersection(node_keywords)
        
        # Calculate Jaccard similarity
        union = query_keywords.union(node_keywords)
        if not union:
            return 0.0
        
        jaccard_score = len(matches) / len(union)
        
        # Also consider what percentage of query keywords were found
        query_coverage = len(matches) / len(query_keywords)
        
        # Combine scores
        final_score = (jaccard_score * 0.3) + (query_coverage * 0.7)
        
        return final_score