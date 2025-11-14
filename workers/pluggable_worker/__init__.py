"""Pluggable Worker Registry

Cloud-only workers that are automatically discovered and registered.
Workers in this folder are excluded from OSS builds.

Architecture:
- OSS: This folder is gitignored and not included in OSS deployments
- Cloud: Workers here are loaded when CLOUD_DEPLOYMENT=true
- Each pluggable worker is independent and follows the same pattern
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def discover_pluggable_workers() -> list[str]:
    """Auto-discover all pluggable workers in this folder.

    This scans the pluggable_worker directory for subdirectories containing
    a worker.py file, indicating a valid worker implementation.

    Returns:
        List[str]: List of worker module names (e.g., ['bulk_download'])
    """
    pluggable_dir = Path(__file__).parent
    workers = []

    try:
        for path in pluggable_dir.iterdir():
            # Skip special directories and files
            if path.name.startswith("_") or path.name.startswith("."):
                continue

            # Check if it's a directory with worker.py
            if path.is_dir() and (path / "worker.py").exists():
                workers.append(path.name)
                logger.debug(f"Discovered pluggable worker: {path.name}")
    except Exception as e:
        logger.error(f"Error discovering pluggable workers: {e}")

    return workers


def is_cloud_deployment() -> bool:
    """Check if this is a cloud deployment with pluggable workers enabled.

    Returns:
        bool: True if cloud deployment, False otherwise
    """
    return os.getenv("CLOUD_DEPLOYMENT", "false").lower() == "true"


def get_available_workers() -> list[str]:
    """Get list of available pluggable workers based on environment.

    Returns:
        List[str]: List of available worker names
    """
    if not is_cloud_deployment():
        logger.info("OSS deployment detected - pluggable workers disabled")
        return []

    workers = discover_pluggable_workers()
    logger.info(f"Found {len(workers)} pluggable workers: {workers}")
    return workers


# Auto-discover workers on module import (for logging)
_available_workers = get_available_workers()

__all__ = [
    "discover_pluggable_workers",
    "is_cloud_deployment",
    "get_available_workers",
]
