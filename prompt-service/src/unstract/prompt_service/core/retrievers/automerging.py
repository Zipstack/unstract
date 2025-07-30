import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters

from unstract.prompt_service.core.retrievers.base_retriever import BaseRetriever
from unstract.prompt_service.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class AutomergingRetriever(BaseRetriever):
    """Automerging retrieval class that automatically merges related chunks
    to provide more comprehensive context.
    """

    def retrieve(self) -> set[str]:
        """Retrieve text chunks using automerging technique.

        This technique retrieves small chunks and automatically merges them
        with adjacent or related chunks to provide better context.

        Returns:
            set[str]: A set of text chunks retrieved from the database.
        """
        try:
            logger.info(
                f"Retrieving chunks for {self.doc_id} using AutomergingRetriever."
            )

            # Get the vector store index
            vector_store_index: VectorStoreIndex = self.vector_db.get_vector_store_index()

            # Create base retriever with metadata filters
            base_retriever = vector_store_index.as_retriever(
                similarity_top_k=self.top_k * 2,  # Get more chunks for merging
                filters=MetadataFilters(
                    filters=[
                        ExactMatchFilter(key="doc_id", value=self.doc_id),
                    ],
                ),
            )

            # Retrieve initial nodes
            initial_nodes: list[NodeWithScore] = base_retriever.retrieve(self.prompt)

            # Group nodes by their source document and position
            grouped_nodes = self._group_nodes_by_position(initial_nodes)

            # Merge adjacent nodes
            merged_nodes = self._merge_adjacent_nodes(grouped_nodes)

            # If we still have too many nodes after merging, select the best ones
            if len(merged_nodes) > self.top_k:
                merged_nodes = sorted(merged_nodes, key=lambda n: n.score, reverse=True)[
                    : self.top_k
                ]

            # Extract unique text chunks
            chunks: set[str] = set()
            for node in merged_nodes:
                if node.score > 0:
                    chunks.add(node.get_content())
                else:
                    logger.info(
                        f"Node score is less than 0. "
                        f"Ignored: {node.node_id} with score {node.score}"
                    )

            logger.info(f"Successfully retrieved {len(chunks)} chunks using automerging.")
            return chunks

        except (ValueError, AttributeError, KeyError, ImportError) as e:
            logger.error(f"Error during automerging retrieval for {self.doc_id}: {e}")
            raise RetrievalError(str(e)) from e
        except Exception as e:
            logger.error(
                f"Unexpected error during automerging retrieval for {self.doc_id}: {e}"
            )
            raise RetrievalError(f"Unexpected error: {str(e)}") from e

    def _group_nodes_by_position(
        self, nodes: list[NodeWithScore]
    ) -> dict[str, list[NodeWithScore]]:
        """Group nodes by their document and position.

        Args:
            nodes: List of nodes to group

        Returns:
            Dictionary mapping document keys to lists of nodes
        """
        grouped = {}

        for node in nodes:
            # Try to extract document and position information from metadata
            metadata = node.node.metadata if hasattr(node.node, "metadata") else {}

            # Create a key based on source document or page
            doc_key = metadata.get("source", "default")
            page_num = metadata.get("page_number", 0)
            key = f"{doc_key}_{page_num}"

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(node)

        # Sort nodes within each group by their position
        for key in grouped:
            grouped[key].sort(
                key=lambda n: (
                    n.node.metadata.get("chunk_index", 0)
                    if hasattr(n.node, "metadata")
                    else 0
                )
            )

        return grouped

    def _merge_adjacent_nodes(
        self, grouped_nodes: dict[str, list[NodeWithScore]]
    ) -> list[NodeWithScore]:
        """Merge adjacent nodes within each group.

        Args:
            grouped_nodes: Dictionary of grouped nodes

        Returns:
            List of merged nodes
        """
        merged_nodes = []

        for key, nodes in grouped_nodes.items():
            if not nodes:
                continue

            # Track which nodes have been merged
            merged_indices = set()

            i = 0
            while i < len(nodes):
                if i in merged_indices:
                    i += 1
                    continue

                current_node = nodes[i]
                merged_content = current_node.get_content()
                merged_score = current_node.score
                merge_count = 1

                # Look for adjacent nodes to merge
                j = i + 1
                while j < len(nodes) and j - i <= 2:  # Merge up to 2 adjacent chunks
                    if j not in merged_indices and self._should_merge(nodes[i], nodes[j]):
                        merged_content += "\n\n" + nodes[j].get_content()
                        merged_score = max(merged_score, nodes[j].score)
                        merged_indices.add(j)
                        merge_count += 1
                    j += 1

                # Create a new merged node
                merged_node = NodeWithScore(
                    node=type(current_node.node)(
                        text=merged_content,
                        id_=f"{current_node.node_id}_merged_{merge_count}",
                        metadata=current_node.node.metadata
                        if hasattr(current_node.node, "metadata")
                        else {},
                    ),
                    score=merged_score,
                )
                merged_nodes.append(merged_node)

                i += 1

        return merged_nodes

    def _should_merge(self, node1: NodeWithScore, node2: NodeWithScore) -> bool:
        """Determine if two nodes should be merged.

        Args:
            node1: First node
            node2: Second node

        Returns:
            True if nodes should be merged
        """
        # Get metadata if available
        metadata1 = node1.node.metadata if hasattr(node1.node, "metadata") else {}
        metadata2 = node2.node.metadata if hasattr(node2.node, "metadata") else {}

        # Check if they're from the same source
        if metadata1.get("source") != metadata2.get("source"):
            return False

        # Check if they're on the same page
        if metadata1.get("page_number") != metadata2.get("page_number"):
            return False

        # Check if they're adjacent chunks
        chunk1 = metadata1.get("chunk_index", -1)
        chunk2 = metadata2.get("chunk_index", -1)

        if chunk1 >= 0 and chunk2 >= 0 and abs(chunk2 - chunk1) == 1:
            return True

        # If no chunk index, check score similarity
        score_diff = abs(node1.score - node2.score)
        if score_diff < 0.1:  # Similar relevance scores
            return True

        return False
