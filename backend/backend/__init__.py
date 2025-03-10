from dotenv import load_dotenv

from .celery_service import app as celery_app

load_dotenv()

__all__ = ["celery_app"]
