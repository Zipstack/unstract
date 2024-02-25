from .snowflake import SnowflakeDB

metadata = {
    "name": SnowflakeDB.__name__,
    "version": "1.0.0",
    "connector": SnowflakeDB,
    "description": "Snowflake connector",
    "is_active": True,
}
