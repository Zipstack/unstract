import os

# app.env reads these at import and raises if any is missing. No test here
# touches the database; the audit model and auth lookups are patched.
for _key, _value in {
    "DB_SCHEMA": "test",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_USERNAME": "test",
    "DB_PASSWORD": "test",
    "DB_NAME": "test",
}.items():
    os.environ.setdefault(_key, _value)
