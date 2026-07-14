import os

# platform_service.env validates required settings at import time.
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("ENCRYPTION_KEY", "test-key")
os.environ.setdefault("DB_SCHEMA", "unstract")
