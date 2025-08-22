from .weaviate import Weaviate

metadata = {
    "name": Weaviate.__name__,
    "version": "1.0.0",
    "adapter": Weaviate,
    "description": "Weaviate VectorDB adapter",
    "is_active": True,
}
