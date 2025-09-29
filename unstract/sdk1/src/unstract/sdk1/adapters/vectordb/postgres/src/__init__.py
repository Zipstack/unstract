from .postgres import Postgres

metadata = {
    "name": Postgres.__name__,
    "version": "1.0.0",
    "adapter": Postgres,
    "description": "Postgres VectorDB adapter",
    "is_active": True,
}
