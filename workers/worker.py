#!/usr/bin/env python
"""Unified Celery Worker Entry Point

This module serves as the main entry point for all Celery workers.
It uses WorkerBuilder to ensure proper configuration including chord retry settings.
"""

import logging
import os
import sys

# Add the workers directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the WorkerBuilder and WorkerType
from shared.enums.worker_enums import WorkerType
from shared.infrastructure import initialize_worker_infrastructure
from shared.infrastructure.config.builder import WorkerBuilder

# Determine worker type from environment FIRST
WORKER_TYPE = os.environ.get("WORKER_TYPE", "general")

# Convert WORKER_TYPE string to WorkerType enum
# Handle directory name mapping: directories use hyphens, enums use underscores
worker_type_mapping = {
    "api-deployment": WorkerType.API_DEPLOYMENT,
    "api_deployment": WorkerType.API_DEPLOYMENT,
    "file_processing": WorkerType.FILE_PROCESSING,
    "file-processing": WorkerType.FILE_PROCESSING,
    "log_consumer": WorkerType.LOG_CONSUMER,
    "log-consumer": WorkerType.LOG_CONSUMER,
    "general": WorkerType.GENERAL,
    "callback": WorkerType.CALLBACK,
    "notification": WorkerType.NOTIFICATION,
    "scheduler": WorkerType.SCHEDULER,
}

# Get the WorkerType enum
worker_type = worker_type_mapping.get(WORKER_TYPE, WorkerType.GENERAL)

# CRITICAL: Setup logging IMMEDIATELY before any logging calls
# This ensures ALL subsequent logs use Django format
WorkerBuilder.setup_logging(worker_type)

# Now get logger after setup is complete
logger = logging.getLogger(__name__)

logger.info("🚀 Unified Worker Entry Point - Using WorkerBuilder System")
logger.info(f"📋 Worker Type: {WORKER_TYPE}")
logger.info(f"🐳 Running from: {os.getcwd()}")
logger.info(f"📦 Converted '{WORKER_TYPE}' to {worker_type}")

# Use WorkerBuilder to create the Celery app with proper configuration
# This ensures chord retry configuration is applied correctly
logger.info(f"🔧 Building Celery app using WorkerBuilder for {worker_type}")
app, config = WorkerBuilder.build_celery_app(worker_type)

# Initialize worker infrastructure (singleton API clients, cache managers, etc.)
# This must happen BEFORE task imports so tasks can use shared infrastructure
logger.info("🏗️ Initializing worker infrastructure (singleton pattern)...")

initialize_worker_infrastructure()
logger.info("✅ Worker infrastructure initialized successfully")

# Import tasks from the worker-specific directory
# Handle directory name mapping for task imports
worker_dir_mapping = {
    WorkerType.API_DEPLOYMENT: "api-deployment",
    WorkerType.FILE_PROCESSING: "file_processing",
    WorkerType.LOG_CONSUMER: "log_consumer",
    WorkerType.GENERAL: "general",
    WorkerType.CALLBACK: "callback",
    WorkerType.NOTIFICATION: "notification",
    WorkerType.SCHEDULER: "scheduler",
}

worker_directory = worker_dir_mapping.get(worker_type, WORKER_TYPE)
worker_path = os.path.join(os.path.dirname(__file__), worker_directory)

# Add worker directory to path for task imports
if os.path.exists(worker_path):
    sys.path.append(worker_path)
    logger.info(f"✅ Added {worker_directory} to Python path for task imports")

    # Import tasks module to register tasks
    tasks_file = os.path.join(worker_path, "tasks.py")
    if os.path.exists(tasks_file):
        logger.info(f"📋 Loading tasks from: {tasks_file}")
        # Import the tasks module to register tasks with the app
        import importlib.util

        spec = importlib.util.spec_from_file_location("tasks", tasks_file)
        tasks_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tasks_module)
        logger.info(f"✅ Tasks loaded successfully from {worker_directory}")
    else:
        logger.warning(f"⚠️ No tasks.py found at: {tasks_file}")
else:
    logger.error(f"❌ Worker directory not found: {worker_path}")

# Log successful configuration
logger.info(f"✅ Successfully loaded {worker_type} worker using WorkerBuilder")
logger.info(
    f"📊 Chord retry interval: {getattr(app.conf, 'result_chord_retry_interval', 'NOT SET')}"
)
logger.info(f"🎯 Worker '{config.worker_name}' ready for Celery")

# Export for Celery to use
__all__ = ["app", "config"]
