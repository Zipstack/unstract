#!/usr/bin/env python
"""Unified Celery Worker Entry Point

This module serves as the main entry point for all Celery workers.
It uses WorkerBuilder to ensure proper configuration including chord retry settings.
"""

import logging
import os
import sys
import threading
import time

from celery import bootsteps

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


# ============= ADD HEARTBEATKEEPER CLASS HERE =============
class HeartbeatKeeper(bootsteps.StartStopStep):
    """Maintains RabbitMQ heartbeat ONLY during warm shutdown to prevent task duplication

    During normal operation: Remains dormant - Celery's built-in heartbeat thread handles everything
    During warm shutdown: Takes over heartbeat duties when Celery's thread stops

    This fixes the issue where RabbitMQ requeues tasks during K8s pod termination
    because Celery stops sending heartbeats during warm shutdown.
    """

    requires = {"celery.worker.components:Pool"}

    def __init__(self, worker, **kwargs):
        self.worker = worker
        self.heartbeat_thread = None
        self.should_stop = threading.Event()
        self._shutdown_in_progress = False

    def start(self, worker):
        """Start heartbeat keeper thread - remains dormant until warm shutdown"""
        # Get configuration for display
        broker_heartbeat = int(os.environ.get("CELERY_BROKER_HEARTBEAT", "10"))
        shutdown_interval = int(
            os.environ.get(
                "HEARTBEAT_KEEPER_SHUTDOWN_INTERVAL", str(max(1, broker_heartbeat // 5))
            )
        )

        logger.info(
            "HeartbeatKeeper: Starting in standby mode (prevents task duplication during shutdown)"
        )
        logger.info(
            "HeartbeatKeeper: Will remain dormant during normal operation - Celery handles heartbeats"
        )
        logger.info(
            f"HeartbeatKeeper: Will activate during warm shutdown (interval: {shutdown_interval}s, broker timeout: {broker_heartbeat}s)"
        )

        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="HeartbeatKeeper",
            daemon=True,  # Daemon thread won't block shutdown
        )
        self.heartbeat_thread.start()

    def stop(self, worker):
        """Called during warm shutdown - keep heartbeat alive"""
        self._shutdown_in_progress = True
        logger.warning(
            "HeartbeatKeeper: Warm shutdown detected - maintaining heartbeat for task completion"
        )
        # Let heartbeat continue during shutdown
        # K8s terminationGracePeriodSeconds handles the timeout

    def terminate(self, worker):
        """Called during final termination"""
        logger.info("HeartbeatKeeper: Final termination - stopping heartbeat thread")
        self.should_stop.set()
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=1)  # Short timeout since daemon thread

    def _heartbeat_loop(self):
        """Maintain heartbeats ONLY during warm shutdown - dormant during normal operation"""
        # Get RabbitMQ heartbeat interval from environment (default 10 seconds)
        broker_heartbeat = int(os.environ.get("CELERY_BROKER_HEARTBEAT", "10"))

        # Shutdown interval should be less than half of broker heartbeat timeout
        # to ensure we send heartbeats frequently enough during shutdown
        shutdown_interval = int(
            os.environ.get(
                "HEARTBEAT_KEEPER_SHUTDOWN_INTERVAL",
                str(
                    max(1, broker_heartbeat // 5)
                ),  # Default to 1/5 of broker heartbeat (e.g., 2s for 10s heartbeat)
            )
        )

        # Normal check interval - how often to check if shutdown started
        normal_check_interval = int(
            os.environ.get(
                "HEARTBEAT_KEEPER_CHECK_INTERVAL",
                str(broker_heartbeat),  # Default to same as broker heartbeat
            )
        )

        # Maximum consecutive errors before logging connection closed
        max_shutdown_errors = int(os.environ.get("HEARTBEAT_KEEPER_MAX_ERRORS", "10"))

        consecutive_shutdown_errors = 0
        last_heartbeat = time.time()
        logged_standby = False

        # Log the configuration on startup (debug level to avoid noise)
        logger.debug(
            f"HeartbeatKeeper config: shutdown_interval={shutdown_interval}s, "
            f"check_interval={normal_check_interval}s, "
            f"broker_heartbeat={broker_heartbeat}s, "
            f"max_errors={max_shutdown_errors}"
        )

        while not self.should_stop.is_set():
            # During normal operation - just sleep, let Celery handle heartbeats
            if not self._shutdown_in_progress:
                if not logged_standby:
                    logger.info(
                        "HeartbeatKeeper: In standby mode - Celery's heartbeat thread is active"
                    )
                    logged_standby = True
                # Just wait and check periodically if shutdown has started
                self.should_stop.wait(normal_check_interval)
                continue

            # Shutdown detected - take over heartbeat duties from Celery
            if logged_standby:
                logger.warning(
                    "HeartbeatKeeper: Taking over heartbeat duties from Celery during warm shutdown"
                )
                logged_standby = False
                last_heartbeat = time.time()  # Reset timer when we start

            # Active heartbeat sending during shutdown
            try:
                if hasattr(self.worker, "consumer") and self.worker.consumer:
                    consumer = self.worker.consumer
                    if consumer.connection and consumer.connection.connected:
                        current_time = time.time()
                        elapsed = current_time - last_heartbeat

                        try:
                            # Use heartbeat_check with rate=0 to force immediate send without validation
                            consumer.connection.heartbeat_check(rate=0)
                            logger.info(
                                f"HeartbeatKeeper: Heartbeat sent during shutdown (elapsed: {elapsed:.1f}s)"
                            )
                            consecutive_shutdown_errors = 0
                            last_heartbeat = current_time

                        except Exception as hb_error:
                            consecutive_shutdown_errors += 1
                            # During shutdown, we expect some errors - log but continue
                            if "Too many heartbeats missed" in str(hb_error):
                                logger.warning(
                                    f"HeartbeatKeeper: Connection degraded during shutdown (attempt {consecutive_shutdown_errors}), continuing..."
                                )
                            else:
                                logger.warning(
                                    f"HeartbeatKeeper: Heartbeat error during shutdown: {hb_error}"
                                )
                            # Don't break the loop during shutdown - keep trying
                            if consecutive_shutdown_errors > max_shutdown_errors:
                                logger.info(
                                    "HeartbeatKeeper: Connection appears closed, but will continue attempts"
                                )

            except (ConnectionError, OSError) as conn_error:
                logger.debug(
                    f"HeartbeatKeeper: Expected connection issue during shutdown: {conn_error}"
                )
            except Exception as e:
                logger.debug(f"HeartbeatKeeper: Error during shutdown (continuing): {e}")

            # Short wait during shutdown for frequent heartbeats
            self.should_stop.wait(shutdown_interval)


# ============= END OF HEARTBEATKEEPER CLASS =============


logger.info("🚀 Unified Worker Entry Point - Using WorkerBuilder System")
logger.info(f"📋 Worker Type: {WORKER_TYPE}")
logger.info(f"🐳 Running from: {os.getcwd()}")
logger.info(f"📦 Converted '{WORKER_TYPE}' to {worker_type}")

# Use WorkerBuilder to create the Celery app with proper configuration
# This ensures chord retry configuration is applied correctly
logger.info(f"🔧 Building Celery app using WorkerBuilder for {worker_type}")
app, config = WorkerBuilder.build_celery_app(worker_type)


# ============= REGISTER HEARTBEATKEEPER HERE =============
# Check if HeartbeatKeeper should be enabled (default: enabled)
heartbeat_keeper_enabled = (
    os.environ.get("HEARTBEAT_KEEPER_ENABLED", "true").lower() == "true"
)

if heartbeat_keeper_enabled:
    # Register the HeartbeatKeeper bootstep
    app.steps["worker"].add(HeartbeatKeeper)
    logger.info(
        "✅ HeartbeatKeeper registered (dormant until warm shutdown) to prevent task duplication"
    )
else:
    logger.info(
        "⚠️ HeartbeatKeeper DISABLED - tasks may be duplicated if worker is terminated during warm shutdown"
    )
# ============= END OF REGISTRATION =============


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
