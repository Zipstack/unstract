from django.core.management.base import BaseCommand
from django.db import connection
from migrating.v2.constants import V2


class Command(BaseCommand):
    help = "Drop v2 schema if it exists"

    def handle(self, *args, **kwargs):
        if not V2.SCHEMA_NAME:
            raise ValueError("SCHEMA_NAME is not defined.")
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {V2.SCHEMA_NAME} CASCADE")
        self.stdout.write(
            self.style.SUCCESS(f'Schema "{V2.SCHEMA_NAME}" deleted successfully.')
        )
