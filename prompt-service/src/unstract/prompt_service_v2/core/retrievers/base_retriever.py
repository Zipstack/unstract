from unstract.sdk.vector_db import VectorDB


class BaseRetriever:
    def __init__(self, vector_db: VectorDB, prompt: str, doc_id: str, top_k: int):
        """Initialize the Retrieval class.

        Args:
            vector_db (VectorDB): The vector database instance.
            prompt (str): The query prompt.
            doc_id (str): Document identifier for query context.
            top_k (int): Number of top results to retrieve.
        """
        self.vector_db = vector_db
        self.prompt = prompt
        self.doc_id = doc_id
        self.top_k = top_k

    @staticmethod
    def retrieve() -> set[str]:
        return set()
