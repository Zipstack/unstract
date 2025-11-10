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

# CRITICAL: Enable gRPC fork support BEFORE any Google API imports
# This must be set before importing any gRPC-based libraries (Google Cloud, etc.)
# to prevent SIGSEGV crashes in forked worker processes
os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "1")
os.environ.setdefault("GRPC_POLL_STRATEGY", "poll")

from celery import bootsteps, signals  # noqa: E402

# Add the workers directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the WorkerBuilder and WorkerType
from shared.enums.worker_enums import WorkerType  # noqa: E402
from shared.infrastructure import initialize_worker_infrastructure  # noqa: E402
from shared.infrastructure.config.builder import WorkerBuilder  # noqa: E402
from shared.models.worker_models import get_celery_setting  # noqa: E402

# Determine worker type from environment FIRST
WORKER_TYPE = os.environ.get("WORKER_TYPE", "general")

# Convert WORKER_TYPE string to WorkerType enum
# Build mapping dynamically from all available WorkerType enum values
# This automatically includes pluggable workers without hardcoding them
worker_type_mapping = {}
for wt in WorkerType:
    # Add both underscore and hyphen versions
    worker_type_mapping[wt.value] = wt
    worker_type_mapping[wt.value.replace("-", "_")] = wt
    worker_type_mapping[wt.value.replace("_", "-")] = wt

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

    def __init__(self, worker, worker_type, **kwargs):
        self.worker = worker
        self.worker_type = worker_type
        self.heartbeat_thread = None
        self.should_stop = threading.Event()
        self._shutdown_in_progress = False

    def start(self, worker):
        """Start heartbeat keeper thread - remains dormant until warm shutdown"""
        # Load all configuration once and store as instance variables
        # Read broker_heartbeat from actual Celery configuration (single source of truth)
        # Default to 10 seconds if None (Celery's default is None)
        self.broker_heartbeat = self.worker.app.conf.broker_heartbeat or 10

        # Get HeartbeatKeeper-specific configuration using hierarchical config system
        self.shutdown_interval = get_celery_setting(
            "HEARTBEAT_KEEPER_SHUTDOWN_INTERVAL",
            self.worker_type,
            max(1, self.broker_heartbeat // 5),
            int,
        )
        self.normal_check_interval = get_celery_setting(
            "HEARTBEAT_KEEPER_CHECK_INTERVAL",
            self.worker_type,
            self.broker_heartbeat,
            int,
        )
        self.max_shutdown_errors = get_celery_setting(
            "HEARTBEAT_KEEPER_MAX_ERRORS", self.worker_type, 10, int
        )

        logger.info(
            "HeartbeatKeeper: Starting in standby mode (prevents task duplication during shutdown)"
        )
        logger.info(
            "HeartbeatKeeper: Will remain dormant during normal operation - Celery handles heartbeats"
        )
        logger.info(
            f"HeartbeatKeeper: Will activate during warm shutdown (interval: {self.shutdown_interval}s, broker timeout: {self.broker_heartbeat}s)"
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

    def _is_connection_ready(self) -> tuple[bool, any]:
        """Check if worker connection is available and ready for heartbeat.

        Returns:
            tuple: (is_ready, consumer_or_none)
        """
        if not hasattr(self.worker, "consumer") or not self.worker.consumer:
            return (False, None)

        consumer = self.worker.consumer
        if not consumer.connection or not consumer.connection.connected:
            return (False, None)

        return (True, consumer)

    def _send_heartbeat_with_error_handling(
        self, consumer: any, consecutive_errors: int, last_heartbeat: float
    ) -> tuple[int, float]:
        """Send heartbeat and handle errors.

        Args:
            consumer: Celery consumer instance
            consecutive_errors: Current count of consecutive errors
            last_heartbeat: Timestamp of last successful heartbeat

        Returns:
            tuple: (updated_consecutive_errors, updated_last_heartbeat)
        """
        current_time = time.time()
        elapsed = current_time - last_heartbeat

        try:
            # Use heartbeat_check with rate=0 to force immediate send without validation
            consumer.connection.heartbeat_check(rate=0)
            logger.info(
                f"HeartbeatKeeper: Heartbeat sent during shutdown (elapsed: {elapsed:.1f}s)"
            )
            return (0, current_time)  # Reset errors on success, update timestamp

        except Exception as hb_error:
            consecutive_errors += 1
            # During shutdown, we expect some errors - log but continue
            if "Too many heartbeats missed" in str(hb_error):
                logger.warning(
                    f"HeartbeatKeeper: Connection degraded during shutdown "
                    f"(attempt {consecutive_errors}), continuing..."
                )
            else:
                logger.warning(
                    f"HeartbeatKeeper: Heartbeat error during shutdown: {hb_error}"
                )

            # Don't break the loop during shutdown - keep trying
            if consecutive_errors > self.max_shutdown_errors:
                logger.info(
                    "HeartbeatKeeper: Connection appears closed, but will continue attempts"
                )

            return (consecutive_errors, last_heartbeat)  # Keep old timestamp on error

    def _attempt_shutdown_heartbeat(
        self, consecutive_errors: int, last_heartbeat: float
    ) -> tuple[int, float]:
        """Attempt to send heartbeat during shutdown with full error handling.

        Args:
            consecutive_errors: Current count of consecutive errors
            last_heartbeat: Timestamp of last successful heartbeat

        Returns:
            tuple: (updated_consecutive_errors, updated_last_heartbeat)
        """
        try:
            is_ready, consumer = self._is_connection_ready()
            if not is_ready:
                return (consecutive_errors, last_heartbeat)

            return self._send_heartbeat_with_error_handling(
                consumer, consecutive_errors, last_heartbeat
            )

        except OSError as conn_error:
            logger.info(
                f"HeartbeatKeeper: Expected connection issue during shutdown: {conn_error}"
            )
        except Exception as e:
            logger.debug(f"HeartbeatKeeper: Error during shutdown (continuing): {e}")

        return (consecutive_errors, last_heartbeat)

    def _wait_in_standby_mode(self, logged_standby: bool) -> tuple[bool, bool]:
        """Handle standby mode during normal operation.

        Args:
            logged_standby: Whether we've already logged standby status

        Returns:
            tuple: (should_continue_loop, updated_logged_standby)
        """
        if not logged_standby:
            logger.info(
                "HeartbeatKeeper: In standby mode - Celery's heartbeat thread is active"
            )
            logged_standby = True

        # Wait and check periodically if shutdown has started
        self.should_stop.wait(self.normal_check_interval)
        return (True, logged_standby)

    def _handle_shutdown_transition(
        self, logged_standby: bool, last_heartbeat: float
    ) -> tuple[bool, float]:
        """Handle transition from standby to active shutdown mode.

        Args:
            logged_standby: Whether we're currently in logged standby state
            last_heartbeat: Current last heartbeat timestamp

        Returns:
            tuple: (updated_logged_standby, updated_last_heartbeat)
        """
        if logged_standby:
            logger.warning(
                "HeartbeatKeeper: Taking over heartbeat duties from Celery during warm shutdown"
            )
            logged_standby = False
            last_heartbeat = time.time()  # Reset timer when we start

        return (logged_standby, last_heartbeat)

    def _heartbeat_loop(self):
        """Maintain heartbeats ONLY during warm shutdown - dormant during normal operation"""
        # Initialize state variables
        consecutive_shutdown_errors = 0
        last_heartbeat = time.time()
        logged_standby = False

        # Log the configuration on startup (debug level to avoid noise)
        logger.debug(
            f"HeartbeatKeeper config: shutdown_interval={self.shutdown_interval}s, "
            f"check_interval={self.normal_check_interval}s, "
            f"broker_heartbeat={self.broker_heartbeat}s, "
            f"max_errors={self.max_shutdown_errors}"
        )

        while not self.should_stop.is_set():
            # During normal operation - just sleep, let Celery handle heartbeats
            if not self._shutdown_in_progress:
                should_continue, logged_standby = self._wait_in_standby_mode(
                    logged_standby
                )
                if should_continue:
                    continue

            # Handle transition from standby to active shutdown mode
            logged_standby, last_heartbeat = self._handle_shutdown_transition(
                logged_standby, last_heartbeat
            )

            # Active heartbeat sending during shutdown
            (
                consecutive_shutdown_errors,
                last_heartbeat,
            ) = self._attempt_shutdown_heartbeat(
                consecutive_shutdown_errors, last_heartbeat
            )

            # Short wait during shutdown for frequent heartbeats
            self.should_stop.wait(self.shutdown_interval)


# ============= END OF HEARTBEATKEEPER CLASS =============


# ============= WORKER-TYPE-AWARE HEARTBEATKEEPER =============
class WorkerTypeAwareHeartbeatKeeper(HeartbeatKeeper):
    """HeartbeatKeeper with worker_type from module context.

    This wrapper class captures the worker_type from the module-level variable
    and passes it to HeartbeatKeeper's __init__. This allows Celery's bootstep
    system to instantiate it with just (worker, **kwargs) while still providing
    the worker_type needed for configuration.
    """

    def __init__(self, worker, **kwargs):
        # worker_type is captured from module scope via closure
        super().__init__(worker, worker_type, **kwargs)


# ============= END OF WORKER-TYPE-AWARE HEARTBEATKEEPER =============


logger.info("🚀 Unified Worker Entry Point - Using WorkerBuilder System")
logger.info(f"📋 Worker Type: {WORKER_TYPE}")
logger.info(f"🐳 Running from: {os.getcwd()}")
logger.info(f"📦 Converted '{WORKER_TYPE}' to {worker_type}")

# Use WorkerBuilder to create the Celery app with proper configuration
# This ensures chord retry configuration is applied correctly
logger.info(f"🔧 Building Celery app using WorkerBuilder for {worker_type}")
app, config = WorkerBuilder.build_celery_app(worker_type)


# ============= WORKER PROCESS INIT HOOK FOR GRPC FORK-SAFETY =============
@signals.worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Initialize worker process after fork to fix gRPC fork-safety issues.

    This signal handler runs in each forked worker process AFTER the fork,
    ensuring that gRPC connections and Google API clients are created fresh
    in the child process, not inherited from the parent.

    Without this, Google Cloud libraries (Drive, GCS, BigQuery, Secret Manager)
    crash with SIGSEGV because they inherit stale gRPC connections from the
    parent process.

    The GRPC_ENABLE_FORK_SUPPORT environment variable set at the top of this
    file enables gRPC's experimental fork support, and this handler ensures
    proper reinitialization after fork.
    """
    import gc

    logger.info("🔄 Worker process initialized after fork (PID: %s)", os.getpid())
    logger.info("🔒 gRPC fork support enabled: GRPC_ENABLE_FORK_SUPPORT=1")
    logger.info(
        "📡 gRPC poll strategy: %s", os.environ.get("GRPC_POLL_STRATEGY", "default")
    )

    # Force garbage collection to clean up any stale gRPC state from parent
    gc.collect()

    logger.info("✅ Worker process ready for gRPC-based operations (Google APIs)")


# ============= END OF WORKER PROCESS INIT HOOK =============


# ============= REGISTER HEARTBEATKEEPER HERE =============
# Check if HeartbeatKeeper should be enabled (default: enabled)
# Uses hierarchical config system: CLI args > worker-specific > global > default
heartbeat_keeper_enabled = get_celery_setting(
    "HEARTBEAT_KEEPER_ENABLED", worker_type, True, bool
)

if heartbeat_keeper_enabled:
    # Register the HeartbeatKeeper bootstep (class defined at module level)
    app.steps["worker"].add(WorkerTypeAwareHeartbeatKeeper)
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
# Determine worker path dynamically based on worker type
base_dir = os.path.dirname(os.path.abspath(__file__))
if worker_type.is_pluggable():
    # Pluggable workers live alongside the workers package at /app/pluggable_worker/{worker_name}
    worker_directory = os.path.join("pluggable_worker", worker_type.value)
    worker_path = os.path.join(os.path.dirname(base_dir), worker_directory)
else:
    # Core workers use their value directly (with hyphens converted to underscores where needed)
    worker_directory = worker_type.value.replace("-", "_")
    worker_path = os.path.join(base_dir, worker_directory)

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
