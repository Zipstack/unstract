import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class FusionRetriever(BaseRetriever):
    """Fusion retrieval class that combines results from multiple queries
    using reciprocal rank fusion.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using query fusion technique.

        This technique generates multiple queries from the original query
        and combines results using reciprocal rank fusion.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(f"Retrieving chunks for {self.doc_id} using FusionRetriever.")

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Generate query variations
            query_variations = self._generate_query_variations(self.prompt)

            # Collect results from all query variations
            all_results = {}

            for i, query in enumerate(query_variations):
                # Create retriever with metadata filters
                retriever = vector_store_index.as_retriever(
                    similarity_top_k=self.top_k,
                    filters=MetadataFilters(
                        filters=[
                            ExactMatchFilter(key="doc_id", value=self.doc_id),
                        ],
                    ),
                )

                # Retrieve nodes for this query variation
                nodes = retriever.retrieve(query)

                # Apply reciprocal rank fusion scoring
                for rank, node in enumerate(nodes):
                    if node.score > 0:
                        node_id = node.node_id
                        # Reciprocal rank fusion formula
                        score = 1.0 / (60 + rank + 1)

                        if node_id in all_results:
                            all_results[node_id] = (
                                all_results[node_id][0],
                                all_results[node_id][1] + score,
                            )
                        else:
                            all_results[node_id] = (node.get_content(), score)

            # Sort by fusion score and get top_k results
            sorted_results = sorted(
                all_results.items(), key=lambda x: x[1][1], reverse=True
            )[: self.top_k]

            # Extract unique text chunks
            chunks: set[str] = {content for _, (content, _) in sorted_results}

            logger.info(f"Successfully retrieved {len(chunks)} chunks using fusion.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during fusion retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during fusion retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e

    def _generate_query_variations(self, original_query: str) -> list[str]:
        """Generate query variations for fusion retrieval.

        Args:
            original_query: The original query string

        Returns:
            List of query variations
        """
        variations = [original_query]

        if self.llm:
            # Use LLM to generate query variations
            try:
                prompt = f"""Generate 3 different variations of this query that ask for the same information in different ways:

Query: {original_query}

Provide only the variations, one per line, without numbering or additional text."""

                response = self.llm.complete(prompt)
                if response and response.text:
                    generated_variations = response.text.strip().split("\n")
                    variations.extend(
                        [v.strip() for v in generated_variations if v.strip()][:3]
                    )
            except (ValueError, AttributeError, KeyError) as e:
                logger.warning(f"Failed to generate query variations with LLM: {e}")
            except Exception as e:
                logger.warning(
                    f"Unexpected error generating query variations with LLM: {e}"
                )

        # If no LLM or LLM failed, use simple transformations
        if len(variations) == 1:
            # Add question mark if not present
            if not original_query.endswith("?"):
                variations.append(original_query + "?")

            # Add "What is" variation
            if not original_query.lower().startswith(
                ("what", "how", "why", "when", "where", "who")
            ):
                variations.append(f"What is {original_query}")

            # Add "Find information about" variation
            variations.append(f"Find information about {original_query}")

        return variations[:4]  # Return maximum 4 variations
