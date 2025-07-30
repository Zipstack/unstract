import logging
import re
from collections import Counter

import nltk
from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from nltk.corpus import stopwords

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class KeywordTableRetriever(BaseRetriever):
    """Keyword table retrieval using keyword extraction and matching.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using keyword-based approach.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using keyword-based retrieval."
            )

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Extract keywords from the query
            keywords = self._extract_keywords(self.prompt)
            
            # If we have keywords, create an enhanced query
            if keywords:
                # Combine original prompt with extracted keywords for better retrieval
                enhanced_query = f"{self.prompt} {' '.join(keywords)}"
            else:
                enhanced_query = self.prompt
            
            # Use vector retriever with the enhanced query
            retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k,
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )
            
            # Retrieve nodes
            nodes = retriever.retrieve(enhanced_query)

            # Extract unique text chunks
            chunks: set[str] = set()
            for node in nodes:
                if node.score > 0:
                    chunks.add(node.get_content())
                else:
                    logger.info(
                        f"Node score is less than 0. "
                        f"Ignored: {node.node_id} with score {node.score}"
                    )

            logger.info(f"Successfully retrieved {len(chunks)} chunks using keyword-based approach.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error during retrieval for {self.doc_id}: {e}")
            raise RetrievalError(f"Unexpected error: {str(e)}") from e

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text using NLTK stopwords and frequency analysis.
        
        Args:
            text: The input text to extract keywords from
            
        Returns:
            list[str]: List of extracted keywords
        """
        # Remove punctuation and convert to lowercase
        clean_text = re.sub(r'[^\w\s]', ' ', text.lower())
        
        # Get stop words using NLTK with fallback
        try:
            stop_words = set(stopwords.words('english'))
        except LookupError:
            # Fallback to a minimal set if NLTK data not available
            logger.warning("NLTK stopwords not available, using fallback list")
            stop_words = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
                'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
                'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those'
            }
        
        # Split into words and filter out stop words
        words = [
            word for word in clean_text.split() 
            if len(word) > 2 and word not in stop_words
        ]
        
        # Count word frequency and return most common
        word_counts = Counter(words)
        
        # Return top keywords (max 10)
        return [word for word, _ in word_counts.most_common(10)]
