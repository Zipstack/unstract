from sqlalchemy.sql import text
import os
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Drop the schema"

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            help="Schema to drop",
        )

    def handle(self, *args, **options):
        schema = options.get("schema")
        if not schema:
            self.stdout.write(self.style.ERROR("Schema name is required"))
            return

        with connection.cursor() as cursor:
            # Use parameterized query instead of string formatting
            cursor.execute("DROP SCHEMA IF EXISTS %s CASCADE", [schema])
            self.stdout.write(self.style.SUCCESS(f"Schema {schema} dropped"))
