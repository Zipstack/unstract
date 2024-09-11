import json
    import logging
    import os
    import time
    from contextlib import contextmanager
    from typing import Any, Generator, Optional

    import psycopg2
    from django.conf import settings
    from django.core.management.base import BaseCommand
    from migrating.v2.constants import V2
    from migrating.v2.unstract_migrations import UnstractMigration
    from psycopg2.extensions import connection, cursor

    logger = logging.getLogger(__name__)


    class DataMigrator:
        def __init__(self, src_db_config, dest_db_config, v2_schema, batch_size=1000):
            self.src_db_config = src_db_config
            self.dest_db_config = dest_db_config
            self.batch_size = batch_size
            self.v2_schema = v2_schema
            self.migration_tracking_table = f"{self.v2_schema}.migration_tracking"

        @contextmanager
        def _db_connect_and_cursor(self, db_config: dict) -> Generator[tuple[connection, cursor], None, None]:
            """A context manager to manage database connection and cursor.

            Args:
                db_config (dict): Database configuration dictionary.

            Yields:
                tuple[connection, cursor]: A tuple containing the connection and cursor.
            """
            conn: connection = psycopg2.connect(**db_config)
            try:
                with conn.cursor() as cur:  # Manage cursor within the same context
                    yield conn, cur
            except psycopg2.Error as e:
                conn.rollback()  # Rollback on error
                logger.error(f"Database operation error: {e}")
                raise
            finally:
                conn.close()

        def _create_tracking_table_if_not_exists(self):
            """Ensures that the migration tracking table exists in the
            destination database.

            Creates the table if it does not exist.
            """
            with self._db_connect_and_cursor(self.dest_db_config) as (conn, cur):
                try:
                    cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {self.migration_tracking_table} (
                            id SERIAL PRIMARY KEY,
                            migration_name VARCHAR(255) UNIQUE NOT NULL,
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """
                    )
                    conn.commit()
                    logger.info("Migration tracking table ensured.")
                except psycopg2.Error as e:
                    logger.error(f"Error creating migration tracking table: {e}")

        def _is_migration_applied(self, migration_name):
            """Checks whether the specified migration has already been applied.

            Args:
                migration_name (str): The name of the migration to check.

            Returns:
                bool: True if the migration has been applied, False otherwise.
            """
            with self._db_connect_and_cursor(self.dest_db_config) as (conn, cur):
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM {self.migration_tracking_table}
                    WHERE migration_name = %s;"
                    """,
                    (migration_name,),
                )
                result = cur.fetchone()
                return result[0] > 0

        def _record_migration(self, migration_name):
            """Records the completion of a migration by inserting its name into
            the tracking table.

            Args:
                migration_name (str): The name of the migration to record.
            """
            with self._db_connect_and_cursor(self.dest_db_config) as (conn, cur):
                cur.execute(
                    f"""
                    INSERT INTO {self.migration_tracking_table} (migration_name)
                    VALUES (%s);
                    """,
                    (migration_name,),
                )
                conn.commit()

        def _fetch_schema_names(
            self, schemas_to_migrate: list[str]
        ) -> list[tuple[int, str]]:
            """Fetches schema names and their IDs from the destination database
            based on the provided schema list. Supports fetching all schemas if
            '_ALL_' is specified.

            Args:
                schemas_to_migrate (list[str]): A list of schema names to migrate, or '_ALL_' to migrate all.

            Returns:
                list[tuple[int, str]]: A list of tuples containing the ID and schema name.
            """
            with self._db_connect_and_cursor(self.dest_db_config) as (conn, cur):

                # Process schemas_to_migrate: trim spaces and remove empty entries
                schemas_to_migrate = [
                    schema.strip() for schema in schemas_to_migrate if schema.strip()
                ]

                # If _ALL_ is present, fetch all schema names
                if schemas_to_migrate == ["_ALL_"]:
                    query = "SELECT id, schema_name FROM account_organization;"
                    cur.execute(query)
                else:
                    placeholders = ",".join(["%s"] * len(schemas_to_migrate))
                    query = (
                        "SELECT id, schema_name FROM account_organization WHERE "
                        f"schema_name IN ({placeholders});"
                    )
                    cur.execute(query, schemas_to_migrate)

                schema_names = [(row[0], row[1]) for row in cur.fetchall()]
                return schema_names

        def _prepare_row_and_migrate_relations(
            self,
            row: tuple[Any, ...],
            dest_cursor: cursor,
            column_names: list[str],
            column_transformations: dict[str, dict[str, Any]],
        ) -> tuple[Any, ...]:
            """Prepares and migrates the relational keys of a single row from
            the source database to the destination database, updating specific
            column values based on provided transformations.

            Args:
                row (tuple[Any, ...]): The row containing the original relational keys.
                dest_cursor (cursor): Cursor for the destination database.
                column_names (list[str]): List of column names in the row.
                column_transformations (dict[str, dict[str, Any]]):
                    A mapping that defines how to transform
                    specific column values (usually foreign keys).
                    The key is the name of the column to be
                    transformed, and the value is a dictionary containing:
                        - query (str): SQL query to fetch the corresponding new value.
                        - params (list[str]): List of column names to use as
                            parameters for the query.
                    This is used to migrate old column names from V1 to new column names in V2.

            Returns:
                tuple[Any, ...]: The row with updated relational keys.
            """
            row = list(row)

            for key, transaction in column_transformations.items():
                if key in column_names:
                    query = transaction["query"]
                    params = transaction["params"]
                    param_values = [row[column_names.index(param)] for param in params]

                    dest_cursor.execute(query, param_values)
                    new_key_value = dest_cursor.fetchone()
                    if new_key_value:
                        row[column_names.index(key)] = new_key_value[0]

            for i, value in enumerate(row):
                if isinstance(value, dict):
                    row[i] = json.dumps(value)
            return tuple(row)

        def _migrate_rows(
            self,
            migration_name: str,
            src_cursor: cursor,
            dest_cursor: cursor,
            dest_conn: connection,
            dest_query: str,
            column_names: list[str],
            column_transformations: dict[str, dict[str, Any]],
        ) -> None:
            """Migrates rows in batches from the source to the destination
            database.

            Args:
                migration_name (str): The name of the migration.
                src_cursor (cursor): Cursor for the source database.
                dest_cursor (cursor): Cursor for the destination database.
                dest_conn (connection): Connection to the destination database.
                dest_query (str): SQL query to insert rows into the destination database.
                column_names (list[str]): List of column names in the source data.
                column_transformations (dict[str, dict[str, Any]]): A mapping that defines key
                    transformations. The key is the name of the column to be transformed, and
                    the value is a dictionary containing:
                        - "query" (str): SQL query to fetch the new value.
                        - "params" (list[str]): List of column names to use as parameters for the query.
                    This is used to migrate old column names from V1 to new column names in V2.

            Returns:
                None
            """
            batch_count = 0
            total_rows = 0

            rows = src_cursor.fetchmany(self.batch_size)
            while rows:
                batch_count += 1
                total_rows += len(rows)
                logger.info(
                    f"[{migration_name}] Processing batch {batch_count}: {len(rows)} rows"
                )

                converted_rows = []
                for row in rows:
                    converted_row = self._prepare_row_and_migrate_relations(
                        row, dest_cursor, column_names, column_transformations
                    )
                    converted_rows.append(converted_row)

                start_time = time.time()
                try:
                    dest_cursor.executemany(dest_query, converted_rows)
                    dest_conn.commit()
                    end_time = time.time()
                    elapsed_time = end_time - start_time
                    logger.info(
                        f"[{migration_name}] Batch {batch_count} inserted successfully."
                        f" Time taken: {elapsed_time:.2f} seconds."
                    )
                except psycopg2.Error as e:
                    dest_conn.rollback()
                    logger.error(
                        f"[{migration_name}] Error inserting batch {batch_count}: {e}"
                    )
                    raise
                # Fetch the next batch of rows
                rows = src_cursor.fetchmany(self.batch_size)
            logger.info(
                f"[{migration_name}] Completed migration with {total_rows} rows processed."
            )

        def _bump_auto_increment_id(
            self, dest_cursor: cursor, dest_table: str, dest_conn: connection
        ) -> None:
            """Adjust the auto-increment ID for a table in the destination
            database.

            This method retrieves the maximum ID value from the specified table
            and sets the next auto-increment value for the table accordingly.
            Args:
                dest_cursor (cursor): The cursor for the destination database.
                dest_table (str): The name of the table to adjust.
                dest_conn (connection): The connection to the destination database.
            Returns:
                None
            """
            try:
                column_type_query = f"""
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema = '{self.v2_schema}' AND table_name = '{dest_table}'
                    AND column_name = 'id';
                """

                dest_cursor.execute(column_type_query)
                result = dest_cursor.fetchone()

                if not result:
                    logger.warning(
                        f"No 'id' column found in table '{dest_table}' in schema "
                        f"'{self.v2_schema}'. Skipping auto-increment adjustment."
                    )
                    return

                column_type = result[0]
                if column_type not in ("bigint", "integer", "serial"):
                    logger.warning(
                        f"Column 'id' in table '{dest_table}' is not of a supported "
                        "type for auto-increment adjustment."
                    )
                    return

                max_id_query = (
                    f'SELECT MAX(id) FROM "{self.v2_schema}".{dest_table};'
                )
                dest_cursor.execute(max_id_query)
                max_id = dest_cursor.fetchone()[0]

                if max_id is None:
                    logger.info(
                        f"Table '{dest_table}' is empty. No need to adjust "
                        "auto-increment."
                    )
                    return

                seq_name = f'"{self.v2_schema}".{dest_table}_id_seq'
                seq_query = f"SELECT setval('{seq_name}', {max_id});"
                dest_cursor.execute(seq_query)
                dest_conn.commit()
                logger.info(
                    f"Adjusted auto-increment for table {dest_table} "
                    f"to start from {max_id + 1}."
                )


            except psycopg2.Error as e:
                dest_conn.rollback()
                logger.error(f"Error adjusting auto-increment for table {dest_table}: {e}")
                raise

        def migrate(
            self, migrations: list[dict[str, str]], organization_id: Optional[str] = None
        ) -> None:
            self._create_tracking_table_if_not_exists()

            with self._db_connect_and_cursor(self.src_db_config) as (src_conn, src_cursor), \
                self._db_connect_and_cursor(self.dest_db_config) as (dest_conn, dest_cursor):

                for migration in migrations:
                    migration_name = migration["name"]
                    logger.info(f"Migration '{migration_name}' started")
                    if self._is_migration_applied(migration_name):
                        logger.info(
                            f"Migration '{migration_name}' has already been applied. "
                            "Skipping..."
                        )
                        continue

                    src_query = migration["src_query"]
                    dest_query = migration["dest_query"]
                    dest_table = migration.get("dest_table")
                    clear_table = migration.get("clear_table", False)
                    column_transformations = migration.get("new_key_transaction", {})

                    # Clear the destination table if specified
                    if clear_table and dest_table:
                        logger.info(f"Clearing table '{dest_table}'")
                        try:
                            start_time = time.time()
                            dest_cursor.execute(f"DELETE FROM {dest_table}")
                            dest_conn.commit()
                            elapsed_time = time.time() - start_time
                            logger.info(
                                f"Table '{dest_table}' cleared successfully. Time taken: "
                                f"{elapsed_time:.2f} seconds."
                            )
                        except Exception as e:
                            logger.error(f"Error clearing table '{dest_table}': {e}")
                            dest_conn.rollback()
                            raise

                    src_cursor.execute(src_query)
                    column_names = [desc[0] for desc in src_cursor.description]

                    self._migrate_rows(
                        migration_name,
                        src_cursor,
                        dest_cursor,
                        dest_conn,
                        dest_query,
                        column_names,
                        column_transformations,
                    )

                    # Adjust the auto-increment value
                    if dest_table and "id" in column_names:
                        self._bump_auto_increment_id(dest_cursor, dest_table, dest_conn)
                    dest_conn.commit()

                    # Record the migration
                    self._record_migration(migration_name, dest_conn)
                    logger.info(f"Migration '{migration_name}' completed successfully")


    class Command(BaseCommand):
        help = "Migrates data from v1 models to v2 models for all apps"

        def handle(self, *args, **options):
            v2_schema = V2.SCHEMA_NAME
            src_db_config = {
                "dbname": settings.DB_NAME,
                "user": settings.DB_USER,
                "password": settings.DB_PASSWORD,
                "host": settings.DB_HOST,
                "port": settings.DB_PORT,
            }
            dest_db_config = {
                "dbname": settings.DB_NAME,
                "user": settings.DB_USER,
                "password": settings.DB_PASSWORD,
                "host": settings.DB_HOST,
                "port": settings.DB_PORT,
            }
            schemas_to_migrate = os.getenv("SCHEMAS_TO_MIGRATE", None)
            migration_query = UnstractMigration(v2_schema=v2_schema)

            # Public tables
            public_schema_migrations = migration_query.get_public_schema_migrations()
            migrator = DataMigrator(
                src_db_config, dest_db_config, v2_schema, batch_size=1000
            )
            migrator.migrate(public_schema_migrations)

            if not schemas_to_migrate:
                    logger.info("Migration not run since SCHEMAS_TO_MIGRATE env seems empty.")
                    return
            else:
                schemas_to_migrate = schemas_to_migrate.split(",")

            # Organization Data (Schema)
            schema_names = migrator._fetch_schema_names(
                schemas_to_migrate=schemas_to_migrate
            )

            for organization_id, schema_name in schema_names:
                if schema_name == "public":
                    logger.info("Skipping public schema migration")
                    continue
                logger.info(
                    f"Migration started for schema_name {schema_name} ID {organization_id}"
                )
                migrations = migration_query.get_organization_migrations(
                    schema=schema_name, organization_id=organization_id
                )
                migrator.migrate(migrations, organization_id)
            completion_message = "DATA MIGRATION COMPLETED SUCCESSFULLY !!!"
            logger.info(completion_message)
