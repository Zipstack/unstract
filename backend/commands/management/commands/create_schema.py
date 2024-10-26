import os

from django.core.management.base import BaseCommand
from django.db import connection

SCHEMA_NAME = os.getenv("DB_SCHEMA", None)


class Command(BaseCommand):
    help = (
        "Create schema if it does not exist. Relies on optional argument '--schema'"
        "or env 'DB_SCHEMA' for the schema name"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            help=(
                "Optional schema name to create. Overrides env 'DB_SCHEMA' if specified"
            ),
        )

    def handle(self, *args, **kwargs):
        schema_name = kwargs["schema"] or os.getenv("DB_SCHEMA")

        if not schema_name:
            raise ValueError(
                "No schema name provided. Set 'DB_SCHEMA' in the environment "
                "or use '--schema' argument."
            )

        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
        self.stdout.write(
            self.style.SUCCESS(f'Schema "{schema_name}" checked/created successfully.')
        )
