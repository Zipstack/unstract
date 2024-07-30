import os

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create v2 schema if it does not exist"

    def handle(self, *args, **kwargs):
        schema_name = os.getenv("V2_SCHEMA_NAME", "unstract_v2")
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
        self.stdout.write(
            self.style.SUCCESS(f'Schema "{schema_name}" checked/created successfully.')
        )
