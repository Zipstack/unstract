#!/usr/bin/env python
"""Unified Celery Worker Entry Point

This module provides a single entry point for all worker types by dynamically
loading the appropriate worker based on WORKER_TYPE environment variable.

Each worker is completely self-contained to avoid circular imports.
"""

import importlib
import logging
import os
import sys

# Add the workers directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logger
logger = logging.getLogger(__name__)

# Determine worker type from environment
WORKER_TYPE = os.environ.get("WORKER_TYPE", "general")

logger.info("🚀 Unified Worker Entry Point")
logger.info(f"📋 Worker Type: {WORKER_TYPE}")
logger.info(
    f"📋 Raw environment WORKER_TYPE: '{os.environ.get('WORKER_TYPE', 'NOT_SET')}'"
)
logger.info(
    f"📋 All WORKER_* env vars: {[(k, v) for k, v in os.environ.items() if k.startswith('WORKER_')]}"
)

# Constants
GENERAL_WORKER_MODULE = "general.worker"

# Map worker types to their actual module names
# Note: api-deployment uses hyphen in directory name
WORKER_MODULE_MAPPING = {
    "api_deployment": "api-deployment.worker",  # Directory: api-deployment
    "general": GENERAL_WORKER_MODULE,  # Directory: general
    "file_processing": "file_processing.worker",  # Directory: file_processing
    "callback": "callback.worker",  # Directory: callback
    "notification": "notification.worker",  # Directory: notification
    "log_consumer": "log_consumer.worker",  # Directory: log_consumer
    "scheduler": "scheduler.worker",  # Directory: scheduler
}

logger.info(f"📋 Available worker types in mapping: {list(WORKER_MODULE_MAPPING.keys())}")

# Get the module name to import
module_name = WORKER_MODULE_MAPPING.get(WORKER_TYPE, GENERAL_WORKER_MODULE)

logger.info(f"📦 Mapping lookup: WORKER_TYPE='{WORKER_TYPE}' -> module='{module_name}'")
logger.info(f"📦 Loading module: {module_name}")

# Import the appropriate worker module
try:
    worker_module = importlib.import_module(module_name)
    app = worker_module.app

    # Also make config available if it exists (for backward compatibility)
    if hasattr(worker_module, "config"):
        config = worker_module.config
        logger.info(f"✅ Successfully loaded {WORKER_TYPE} worker with config")
    else:
        config = None
        logger.info(f"✅ Successfully loaded {WORKER_TYPE} worker (no config)")

except ImportError as e:
    logger.error(f"❌ Error loading worker module '{module_name}': {e}")
    logger.error(f"❌ Import error details: {type(e).__name__}: {str(e)}")
    import traceback

    logger.error(f"❌ Full traceback: {traceback.format_exc()}")
    logger.info("🔄 Falling back to general worker")

    # Fall back to general worker
    try:
        from general.worker import app

        worker_module = importlib.import_module(GENERAL_WORKER_MODULE)
        if hasattr(worker_module, "config"):
            config = worker_module.config
        else:
            config = None
        logger.info("✅ Fallback successful - using general worker")
    except Exception as fallback_error:
        logger.critical(
            f"💥 Critical: Cannot load fallback general worker: {fallback_error}"
        )
        raise

logger.info("🎯 Worker app ready for Celery")

# Export for Celery to use
__all__ = ["app", "config"]
