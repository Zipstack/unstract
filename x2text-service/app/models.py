import datetime
import uuid
from os import environ as env

import peewee

PG_BE_HOST = env.get("DB_HOST")
PG_BE_PORT = int(env.get("DB_PORT", 5432))
PG_BE_USERNAME = env.get("DB_USERNAME")
PG_BE_PASSWORD = env.get("DB_PASSWORD")
PG_BE_DATABASE = env.get("DB_NAME")


be_db = peewee.PostgresqlDatabase(
    PG_BE_DATABASE,
    user=PG_BE_USERNAME,
    password=PG_BE_PASSWORD,
    host=PG_BE_HOST,
    port=PG_BE_PORT,
)


class X2TextAudit(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = peewee.DateTimeField(default=datetime.datetime.now)
    org_id = peewee.CharField()
    file_name = peewee.CharField()
    file_type = peewee.CharField()
    file_size_in_kb = peewee.FloatField()
    status = peewee.CharField(default="")

    class Meta:
        database = be_db  # This model uses the "BE_DB" database.
        table_name = "x2text_audit"
