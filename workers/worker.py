#!/usr/bin/env python
"""Unified Celery Worker Entry Point

This module provides a single entry point for all worker types by dynamically
loading the appropriate worker based on WORKER_TYPE environment variable.

Each worker is completely self-contained to avoid circular imports.
"""

import importlib
import os
import sys

# Add the workers directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Determine worker type from environment
WORKER_TYPE = os.environ.get("WORKER_TYPE", "general")

print("🚀 Unified Worker Entry Point")
print(f"📋 Worker Type: {WORKER_TYPE}")

# Map worker types to their actual module names
# Note: api-deployment uses hyphen in directory name
WORKER_MODULE_MAPPING = {
    "api_deployment": "api-deployment.worker",  # Directory: api-deployment
    "general": "general.worker",  # Directory: general
    "file_processing": "file_processing.worker",  # Directory: file_processing
    "callback": "callback.worker",  # Directory: callback
    "notification": "notification.worker",  # Directory: notification
    "log_consumer": "log_consumer.worker",  # Directory: log_consumer
}

# Get the module name to import
module_name = WORKER_MODULE_MAPPING.get(WORKER_TYPE, "general.worker")

print(f"📦 Loading module: {module_name}")

# Import the appropriate worker module
try:
    worker_module = importlib.import_module(module_name)
    app = worker_module.app

    # Also make config available if it exists (for backward compatibility)
    if hasattr(worker_module, "config"):
        config = worker_module.config
        print(f"✅ Successfully loaded {WORKER_TYPE} worker with config")
    else:
        config = None
        print(f"✅ Successfully loaded {WORKER_TYPE} worker (no config)")

except ImportError as e:
    print(f"❌ Error loading worker module '{module_name}': {e}")
    print("🔄 Falling back to general worker")

    # Fall back to general worker
    try:
        from general.worker import app

        worker_module = importlib.import_module("general.worker")
        if hasattr(worker_module, "config"):
            config = worker_module.config
        else:
            config = None
        print("✅ Fallback successful - using general worker")
    except Exception as fallback_error:
        print(f"💥 Critical: Cannot load fallback general worker: {fallback_error}")
        raise

print("🎯 Worker app ready for Celery")

# Export for Celery to use
__all__ = ["app", "config"]
