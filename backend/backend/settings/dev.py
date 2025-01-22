from backend.settings.base import *  # noqa: F401, F403

DEBUG = True

X_FRAME_OPTIONS = "http://localhost:3000"
X_FRAME_OPTIONS = "ALLOW-FROM http://localhost:3000"

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://unstract.because-security.com",
    # Other allowed origins if needed
]

CORS_ORIGIN_WHITELIST = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://unstract.because-security.com",
    # Other allowed origins if needed
]

CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
]
