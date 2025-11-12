import datetime
import logging
import os
import tempfile
import zipfile
from typing import TYPE_CHECKING, Any

import oracledb
from oracledb.connection import Connection

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile

from unstract.connectors.constants import DatabaseTypeConstants
from unstract.connectors.databases.unstract_db import UnstractDB

logger = logging.getLogger(__name__)


class OracleDB(UnstractDB):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("OracleDB")

        self.user = settings.get("user", "admin")
        self.password = settings.get("password", "")
        self.dsn = settings.get("dsn", "")
        self.wallet_password = settings.get("wallet_password", "")
        self._temp_wallet_dir: str | None = None

        # Require wallet file upload
        wallet_file = settings.get("wallet_file")
        if not wallet_file:
            raise ValueError(
                "Oracle wallet file is required. Please upload a wallet ZIP file containing ewallet.pem, tnsnames.ora, and other Oracle configuration files."
            )

        # Extract wallet file and use same directory for both config and wallet
        wallet_dir = self._extract_wallet_file(wallet_file)
        self.config_dir = wallet_dir
        self.wallet_location = wallet_dir
        logger.info("Using uploaded wallet directory: %s", wallet_dir)

        if not (
            self.config_dir
            and self.user
            and self.password
            and self.dsn
            and self.wallet_location
            and self.wallet_password
        ):
            raise ValueError("Ensure all connection parameters are provided.")

    def _extract_wallet_file(self, wallet_file: "UploadedFile") -> str:
        """Extract ZIP wallet file to a temporary directory.

        The extracted directory contains all Oracle wallet files (ewallet.pem for SSL/TLS,
        tnsnames.ora for connection names, sqlnet.ora for SQL*Net config, etc.) and serves
        as the single source for all Oracle configuration.

        Args:
            wallet_file: Django UploadedFile object

        Returns:
            str: Path to the temporary directory containing all extracted wallet files

        Raises:
            ValueError: If the wallet file is invalid or cannot be extracted
        """
        # Create a temporary directory for wallet files
        self._temp_wallet_dir = tempfile.mkdtemp(prefix="oracle_wallet_")

        logger.info(
            "Processing Django UploadedFile: %s", getattr(wallet_file, "name", "unknown")
        )

        # Save uploaded file to temporary ZIP file and extract
        temp_fd, temp_wallet_path = tempfile.mkstemp(
            suffix=".zip", prefix="oracle_wallet_"
        )

        try:
            with os.fdopen(temp_fd, "wb") as temp_file:
                for chunk in wallet_file.chunks():
                    temp_file.write(chunk)

            with zipfile.ZipFile(temp_wallet_path, "r") as zip_ref:
                zip_ref.extractall(self._temp_wallet_dir)

        except zipfile.BadZipFile:
            raise ValueError("Invalid ZIP file provided for Oracle wallet.")
        except Exception as e:
            logger.error("Failed to extract Oracle wallet file: %s", str(e))
            raise ValueError(f"Failed to extract Oracle wallet file: {str(e)}")
        finally:
            # Always clean up temporary file
            if os.path.exists(temp_wallet_path):
                os.unlink(temp_wallet_path)

        logger.info("Oracle wallet ZIP file extracted to %s", self._temp_wallet_dir)
        return self._temp_wallet_dir

    def __del__(self) -> None:
        """Cleanup temporary wallet directory when the object is destroyed."""
        if hasattr(self, "_temp_wallet_dir") and self._temp_wallet_dir:
            try:
                import shutil

                shutil.rmtree(self._temp_wallet_dir)
                logger.info(
                    "Cleaned up temporary wallet directory: %s", self._temp_wallet_dir
                )
            except Exception as e:
                logger.warning("Failed to cleanup temporary wallet directory: %s", str(e))

    @staticmethod
    def get_id() -> str:
        return "oracledb|49e3b4c1-9c34-43fc-89a4-96950821ade0"

    @staticmethod
    def get_name() -> str:
        return "OracleDB"

    @staticmethod
    def get_description() -> str:
        return "oracledb Database"

    @staticmethod
    def get_icon() -> str:
        return "/icons/connector-icons/Oracle.png"

    @staticmethod
    def get_json_schema() -> str:
        f = open(f"{os.path.dirname(__file__)}/static/json_schema.json")
        schema = f.read()
        f.close()
        return schema

    @staticmethod
    def can_write() -> bool:
        return True

    @staticmethod
    def can_read() -> bool:
        return True

    def get_engine(self) -> Connection:
        con: Connection = oracledb.connect(
            config_dir=self.config_dir,
            user=self.user,
            password=self.password,
            dsn=self.dsn,
            wallet_location=self.wallet_location,
            wallet_password=self.wallet_password,
        )
        return con

    def sql_to_db_mapping(self, value: Any, column_name: str | None = None) -> str:
        """Function to generate information schema of the corresponding table.

        Args:
            value (Any): python value of any datatype
            column_name (str | None): name of the column being mapped

        Returns:
            str: database columntype
        """
        data_type = type(value)
        if data_type in (dict, list):
            if column_name and column_name.endswith("_v2"):
                return str(DatabaseTypeConstants.ORACLE_CLOB)
            else:
                return str(DatabaseTypeConstants.ORACLE_VARCHAR2)

        mapping = {
            str: DatabaseTypeConstants.ORACLE_VARCHAR2,
            int: DatabaseTypeConstants.ORACLE_NUMBER,
            float: DatabaseTypeConstants.ORACLE_LONG,
            datetime.datetime: DatabaseTypeConstants.ORACLE_TIMESTAMP,
        }
        return str(mapping.get(data_type, DatabaseTypeConstants.ORACLE_VARCHAR2))

    def get_create_table_base_query(self, table: str) -> str:
        """Function to create a base create table sql query.

        Args:
            table (str): db-connector table name

        Returns:
            str: generates a create sql base query with the constant columns
        """
        sql_query = (
            f"CREATE TABLE {table} "
            f"(id VARCHAR2(32767) , "
            f"created_by VARCHAR2(32767), created_at TIMESTAMP, "
            f"metadata CLOB, "
            f"user_field_1 NUMBER(1) DEFAULT 0, "
            f"user_field_2 NUMBER DEFAULT 0, "
            f"user_field_3 VARCHAR2(32767) DEFAULT NULL, "
            f"status VARCHAR2(10), "
            f"error_message VARCHAR2(32767), "
        )
        return sql_query

    def prepare_multi_column_migration(
        self, table_name: str, column_name: str
    ) -> list[str]:
        """Prepare ALTER TABLE statements for adding new columns to an existing table.

        Args:
            table_name (str): The name of the table to alter
            column_name (str): The base name of the column to add a _v2 version for

        Returns:
            list: List of ALTER TABLE statements, one per column addition

        Note:
            Oracle does not support multiple ADD clauses in a single ALTER TABLE statement.
            Each column addition requires a separate ALTER TABLE statement.
        """
        # Return one ALTER statement per column for Oracle compatibility
        return [
            f"ALTER TABLE {table_name} ADD {column_name}_v2 CLOB",
            f"ALTER TABLE {table_name} ADD metadata CLOB",
            f"ALTER TABLE {table_name} ADD user_field_1 NUMBER(1) DEFAULT 0",
            f"ALTER TABLE {table_name} ADD user_field_2 NUMBER DEFAULT 0",
            f"ALTER TABLE {table_name} ADD user_field_3 VARCHAR2(32767) DEFAULT NULL",
            f"ALTER TABLE {table_name} ADD status VARCHAR2(10)",
            f"ALTER TABLE {table_name} ADD error_message VARCHAR2(32767)",
        ]

    @staticmethod
    def get_sql_insert_query(
        table_name: str, sql_keys: list[str], sql_values: list[str] | None = None
    ) -> str:
        """Function to generate parameterised insert sql query.

        Args:
            table_name (str): db-connector table name
            sql_keys (list[str]): column names
            sql_values (list[str], optional): SQL values for database-specific handling (ignored for Oracle)

        Returns:
            str: returns a string with parameterised insert sql query
        """
        columns = ", ".join(sql_keys)
        values = []
        for key in sql_keys:
            if key == "created_at":
                values.append("TO_TIMESTAMP(:created_at, 'YYYY-MM-DD HH24:MI:SS.FF')")
            else:
                values.append(f":{key}")
        return f"INSERT INTO {table_name} ({columns}) VALUES ({', '.join(values)})"

    def execute_query(
        self, engine: Any, sql_query: str, sql_values: Any, **kwargs: Any
    ) -> None:
        """Executes create/insert query with Oracle-specific error handling.

        Args:
            engine (Any): oracle db client engine
            sql_query (str): sql create table/insert into table query
            sql_values (Any): sql data to be insertted
        """
        sql_keys = list(kwargs.get("sql_keys", []))
        with engine.cursor() as cursor:
            try:
                if sql_values:
                    params = dict(zip(sql_keys, sql_values, strict=False))
                    cursor.execute(sql_query, params)
                else:
                    cursor.execute(sql_query)
                engine.commit()
            except oracledb.DatabaseError as e:
                logger.debug(f"Oracle database error occurred: {str(e)}")
                if "ORA-00955" in str(e):
                    logger.info("Table already exists (ORA-00955) for oracle-db")
                else:
                    raise

    def get_information_schema(self, table_name: str) -> dict[str, str]:
        """Function to generate information schema of the big query table.

        Args:
            table_name (str): db-connector table name

        Returns:
            dict[str, str]: a dictionary contains db column name and
            db column types of corresponding table
        """
        query = (
            "SELECT column_name, data_type FROM "
            "user_tab_columns WHERE "
            f"table_name = UPPER('{table_name}')"
        )
        results = self.execute(query=query)
        column_types: dict[str, str] = self.get_db_column_types(
            columns_with_types=results
        )
        return column_types
