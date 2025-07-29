"""Unstract Workers Package

Lightweight Celery workers for distributed task processing.
"""

__version__ = "1.0.0"
__author__ = "Unstract Team"
__email__ = "support@unstract.com"

# Import only shared module to avoid circular imports
# Individual worker modules are imported as needed

__all__ = [
    "shared",
    "api_deployment",
    "general",
    "file_processing",
    "callback",
]
