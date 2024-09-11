from django.core.management.base import BaseCommand
from django.db import connection
from migrating.v2.constants import V2


class Command(BaseCommand):
    help = "Create v2 schema if it does not exist"

    def handle(self, *args, **kwargs):
        if not V2.SCHEMA_NAME:
            raise ValueError("SCHEMA_NAME is not defined.")
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {V2.SCHEMA_NAME}")
        self.stdout.write(
            self.style.SUCCESS(
                f'Schema "{V2.SCHEMA_NAME}" checked/created successfully.'
            )
        )
