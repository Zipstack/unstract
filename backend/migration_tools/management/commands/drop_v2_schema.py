import os

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Drop v2 schema if it exists"

    def handle(self, *args, **kwargs):
        schema_name = os.getenv("V2_SCHEMA_NAME", "unstract_v2")
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
        self.stdout.write(
            self.style.SUCCESS(f'Schema "{schema_name}" deleted successfully.')
        )
