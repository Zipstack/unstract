import datetime
import uuid

import peewee
from app.env import Env

be_db = peewee.PostgresqlDatabase(
    Env.DB_NAME,
    user=Env.DB_USERNAME,
    password=Env.DB_PASSWORD,
    host=Env.DB_HOST,
    port=Env.DB_PORT,
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
        schema = Env.DB_SCHEMA
