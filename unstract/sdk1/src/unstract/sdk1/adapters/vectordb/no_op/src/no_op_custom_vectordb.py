import time

from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.types import VectorStore, VectorStoreQueryResult


class NoOpCustomVectorDB(VectorStore):
    stores_text: bool = True
    stores_node: bool = True
    is_embedding_query: bool = True
    wait_time: float = 0

    def __init__(
        self,
        wait_time: float,
        dim: int,
    ) -> None:
        """Initialize params."""
        self.wait_time = wait_time
        self.dim = dim

    def query(self, query: object, **kwargs: object) -> VectorStoreQueryResult:
        """Query vector store."""
        node1 = TextNode(text="This is a dummy document.", id_="1")
        similarity_scores = [0.9]
        embeddings = ["test"]  # Dummy embeddings for each node

        query_result = VectorStoreQueryResult(
            nodes=[node1], similarities=similarity_scores, ids=embeddings
        )
        time.sleep(self.wait_time)
        return query_result
