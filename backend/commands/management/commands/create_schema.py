from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create schema for the database"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Creating schema..."))
        with connection.cursor() as cursor:
            # Create schema
            cursor.execute("CREATE SCHEMA IF NOT EXISTS unstract")

            # Create tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS unstract.users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS unstract.documents (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES unstract.users(id)
                )
                """
            )

            # Use parameterized query for dynamic table creation
            table_name = "unstract.summaries"
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS %s (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (document_id) REFERENCES unstract.documents(id)
                )
                """, 
                [table_name]
            )

        self.stdout.write(self.style.SUCCESS("Schema created successfully!"))
