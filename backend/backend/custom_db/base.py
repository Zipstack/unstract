import logging

from django.conf import settings
from django.db.backends.postgresql.base import (
    DatabaseWrapper as PostgresDatabaseWrapper,
)

logger = logging.getLogger(__name__)


class DatabaseWrapper(PostgresDatabaseWrapper):
    """Custom DatabaseWrapper to manage PostgreSQL connections and set the
    search path."""

    def get_new_connection(self, conn_params):
        """Establish a new database connection or reuse an existing one, and
        set the search path.

        Args:
            conn_params: Parameters for the new database connection.

        Returns:
            connection: The database connection
        """
        connection = super().get_new_connection(conn_params)
        logger.info(f"DB connection (ID: {id(connection)}) is established or reused.")
        self.set_search_path(connection)
        return connection

    def set_search_path(self, connection):
        """Set the search path for the given database connection.

        This ensures that the database queries will look in the specified schema.

        Args:
            connection: The database connection for which to set the search path.
        """
        conn_id = id(connection)
        original_autocommit = connection.autocommit
        try:
            connection.autocommit = True
            logger.debug(
                f"Setting search_path to {settings.DB_SCHEMA} for DB connection ID "
                f"{conn_id}."
            )
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {settings.DB_SCHEMA}")
            logger.debug(
                f"Successfully set search_path for DB connection ID {conn_id}."
            )
        finally:
            connection.autocommit = original_autocommit
