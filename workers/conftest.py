"""Root conftest for workers test suite.

Sets required environment variables before any workers modules are imported.
"""

import os

# These must be set before any workers module import because
# shared/constants/api_endpoints.py evaluates INTERNAL_API_BASE_URL at class definition time.
os.environ.setdefault("INTERNAL_API_BASE_URL", "http://test-backend:8000/internal")
os.environ.setdefault("INTERNAL_SERVICE_API_KEY", "test-key-123")
os.environ.setdefault("CELERY_BROKER_BASE_URL", "amqp://localhost:5672//")
os.environ.setdefault("CELERY_BROKER_USER", "guest")
os.environ.setdefault("CELERY_BROKER_PASS", "guest")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "testdb")
