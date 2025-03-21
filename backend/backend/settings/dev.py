from backend.settings.base import *  # noqa: F403

DEBUG = True

X_FRAME_OPTIONS = "http://localhost:3000"
X_FRAME_OPTIONS = "ALLOW-FROM http://localhost:3000"

# Add to the CORS_ALLOWED_ORIGINS from base
CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS + [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://frontend.unstract.localhost",
    # Other allowed origins if needed
]
