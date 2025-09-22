class Common:
    METADATA = "metadata"
    MODULE = "module"
    CONNECTOR = "connector"


class DatabaseTypeConstants:
    """Central location for all database-specific type constants."""

    # BigQuery types
    BIGQUERY_JSON: str = "JSON"
    BIGQUERY_STRING: str = "STRING"
    BIGQUERY_INT64: str = "INT64"
    BIGQUERY_FLOAT64: str = "FLOAT64"
    BIGQUERY_TIMESTAMP: str = "TIMESTAMP"

    # PostgreSQL types
    POSTGRES_JSONB: str = "JSONB"
    POSTGRES_TEXT: str = "TEXT"
    POSTGRES_INTEGER: str = "INTEGER"
    POSTGRES_DOUBLE_PRECISION: str = "DOUBLE PRECISION"
    POSTGRES_TIMESTAMP: str = "TIMESTAMP"

    # Snowflake types
    SNOWFLAKE_VARIANT: str = "VARIANT"
    SNOWFLAKE_TEXT: str = "TEXT"
    SNOWFLAKE_INT: str = "INT"
    SNOWFLAKE_FLOAT: str = "FLOAT"
    SNOWFLAKE_TIMESTAMP: str = "TIMESTAMP"

    # MySQL types
    MYSQL_JSON: str = "JSON"
    MYSQL_LONGTEXT: str = "LONGTEXT"
    MYSQL_BIGINT: str = "BIGINT"
    MYSQL_FLOAT: str = "FLOAT"
    MYSQL_TIMESTAMP: str = "TIMESTAMP"

    # Redshift types
    REDSHIFT_SUPER: str = "SUPER"
    REDSHIFT_VARCHAR: str = "VARCHAR(65535)"
    REDSHIFT_BIGINT: str = "BIGINT"
    REDSHIFT_DOUBLE_PRECISION: str = "DOUBLE PRECISION"
    REDSHIFT_TIMESTAMP: str = "TIMESTAMP"

    # MSSQL types
    MSSQL_NVARCHAR_MAX: str = "NVARCHAR(MAX)"
    MSSQL_INT: str = "INT"
    MSSQL_FLOAT: str = "FLOAT"
    MSSQL_DATETIMEOFFSET: str = "DATETIMEOFFSET"

    # Oracle types
    ORACLE_CLOB: str = "CLOB"
    ORACLE_VARCHAR2: str = "VARCHAR2(32767)"
    ORACLE_NUMBER: str = "NUMBER"
    ORACLE_LONG: str = "LONG"
    ORACLE_TIMESTAMP: str = "TIMESTAMP"
