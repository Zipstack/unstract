"""Extraction module for document chunking and embedding generation.

This module provides celery tasks for the document extraction pipeline,
handling text chunking and embedding generation as part of the agentic
data extraction process.
"""

from .chunking_embedding_task import process_chunking_and_embedding
from .token_helper import TokenCalculationHelper

__all__ = [
    "process_chunking_and_embedding",
    "TokenCalculationHelper",
]

# Celery task registration information
CELERY_TASKS = {
    "chunking_embedding_task": {
        "task": process_chunking_and_embedding,
        "name": "chunking_embedding_task",
        "queue": "processing_queue",  # Can be configured based on requirements
        "routing_key": "extraction.chunking",
        "priority": 5,  # Medium priority
        "rate_limit": "100/m",  # Rate limiting if needed
        "time_limit": 3600,  # 1 hour timeout
        "soft_time_limit": 3300,  # Soft limit at 55 minutes
    }
}

# Module metadata
__version__ = "0.1.0"
__author__ = "Unstract Team"
__description__ = "Document chunking and embedding extraction tasks"
