from .postgresql import PostgreSQL

metadata = {
    "name": PostgreSQL.__name__,
    "version": "1.0.0",
    "connector": PostgreSQL,
    "description": "PostgreSQL connector",
    "is_active": True,
}
