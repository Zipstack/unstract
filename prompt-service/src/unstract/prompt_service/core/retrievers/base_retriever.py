from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status("sdk1"):
    from unstract.sdk1.llm import LLM
    from unstract.sdk1.vector_db import VectorDB
else:
    from unstract.sdk.llm import LLM
    from unstract.sdk.vector_db import VectorDB


class BaseRetriever:
    def __init__(
        self,
        vector_db: VectorDB,
        prompt: str,
        doc_id: str,
        top_k: int,
        llm: LLM | None = None,
    ):
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
        if check_feature_flag_status("sdk1"):
            self.llm = llm if llm else None
        else:
            self.llm = llm._llm_instance if llm else None

    @staticmethod
    def retrieve() -> set[str]:
        return set()
