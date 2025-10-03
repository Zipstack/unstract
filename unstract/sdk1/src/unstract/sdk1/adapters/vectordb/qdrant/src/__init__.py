from .qdrant import Qdrant

metadata = {
    "name": Qdrant.__name__,
    "version": "1.0.0",
    "adapter": Qdrant,
    "description": "Qdrant VectorDB adapter",
    "is_active": True,
}

__all__ = ["Qdrant"]
