from .oracle_db import OracleDB

metadata = {
    "name": OracleDB.__name__,
    "version": "1.0.0",
    "connector": OracleDB,
    "description": "OracleDB connector",
    "is_active": True,
}
