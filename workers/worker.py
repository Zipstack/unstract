#!/usr/bin/env python
"""Unified Celery Worker Entry Point

Direct loading of new refactored worker system.
No fallbacks - if it fails, it should fail clearly with real errors.
"""

import importlib.util
import logging
import os
import sys

from celery import Celery

# Add the workers directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logger
logger = logging.getLogger(__name__)

# Determine worker type from environment
WORKER_TYPE = os.environ.get("WORKER_TYPE", "general")

logger.info("🚀 Unified Worker Entry Point - New Refactored System")
logger.info(f"📋 Worker Type: {WORKER_TYPE}")
logger.info(f"🐳 Running from: {os.getcwd()}")
logger.info(f"🐍 Python Path: {sys.path[:3]}...")  # Show first 3 entries

# Import the new refactored system directly - no fallbacks
# Import directly from modules to avoid complex __init__ chains

sys.path.append(os.path.join(os.path.dirname(__file__), "shared"))

# Import WorkerConfig and enums directly without package __init__ chains

# Import WorkerConfig directly from file
worker_config_path = os.path.join(
    os.path.dirname(__file__), "shared", "infrastructure", "config", "worker_config.py"
)
worker_config_spec = importlib.util.spec_from_file_location(
    "worker_config", worker_config_path
)
worker_config_module = importlib.util.module_from_spec(worker_config_spec)
worker_config_spec.loader.exec_module(worker_config_module)
WorkerConfig = worker_config_module.WorkerConfig

# Import WorkerType enum directly
worker_enums_path = os.path.join(
    os.path.dirname(__file__), "shared", "enums", "worker_enums.py"
)
worker_enums_spec = importlib.util.spec_from_file_location(
    "worker_enums", worker_enums_path
)
worker_enums_module = importlib.util.module_from_spec(worker_enums_spec)
worker_enums_spec.loader.exec_module(worker_enums_module)
WorkerType = worker_enums_module.WorkerType

logger.info("🔧 Loading new refactored worker system")

# Convert WORKER_TYPE string to WorkerType enum
worker_type = WorkerType.from_directory_name(WORKER_TYPE)
logger.info(f"📦 Converted '{WORKER_TYPE}' to {worker_type}")

# Create worker config directly to avoid complex builder imports
config = WorkerConfig()

# Create basic Celery app directly

# Import tasks directly by adding the worker directory to path
# Handle directory name mapping: worker type uses underscores, directories use hyphens
worker_dir_mapping = {
    "api_deployment": "api-deployment",
    "file_processing": "file_processing",
    "log_consumer": "log_consumer",
    "general": "general",
    "callback": "callback",
    "notification": "notification",
    "scheduler": "scheduler",
}

worker_directory = worker_dir_mapping.get(WORKER_TYPE, WORKER_TYPE)
worker_path = os.path.join(os.path.dirname(__file__), worker_directory)
logger.info(f"🗂️ Worker directory: {worker_directory}")
logger.info(f"📁 Worker path: {worker_path}")

# Verify the tasks.py file exists
tasks_file = os.path.join(worker_path, "tasks.py")
if os.path.exists(tasks_file):
    logger.info(f"✅ Found tasks.py at: {tasks_file}")
else:
    logger.error(f"❌ Missing tasks.py at: {tasks_file}")
    logger.error(
        f"Available files: {os.listdir(worker_path) if os.path.exists(worker_path) else 'Directory not found'}"
    )

sys.path.append(worker_path)

app = Celery(
    config.worker_name,
    broker=config.celery_broker_url,
    backend=config.celery_result_backend,
    include=["tasks"],  # Import tasks from the current worker directory
)

# Configure the Celery app
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)

logger.info(f"✅ Successfully loaded {WORKER_TYPE} worker using simplified system")
logger.info("🎯 Worker app ready for Celery")

# Export for Celery to use
__all__ = ["app", "config"]
