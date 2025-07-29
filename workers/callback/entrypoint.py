#!/usr/bin/env python3
"""Entrypoint for Callback Worker with Health Server Integration

This entrypoint ensures health servers start properly when running via Docker.
"""

import signal
import sys

from worker import app, config, health_server, logger


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    try:
        if config.enable_health_server:
            health_server.stop()
    except Exception as e:
        logger.error(f"Error stopping health server: {e}")
    sys.exit(0)


def main():
    """Main entrypoint that starts health server and Celery worker."""
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Start health server only if enabled
        if config.enable_health_server:
            health_server.start()
            logger.info("Health server started successfully")
        else:
            logger.info("Health server disabled via ENABLE_HEALTH_SERVER=false")

        # Start Celery worker with original arguments
        celery_args = (
            sys.argv[1:]
            if len(sys.argv) > 1
            else [
                "worker",
                "--loglevel=info",
                "--queues=file_processing_callback,api_file_processing_callback",
            ]
        )

        logger.info(f"Starting Celery worker with args: {celery_args}")
        app.worker_main(argv=celery_args)

    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise
    finally:
        try:
            if config.enable_health_server:
                health_server.stop()
        except Exception as e:
            logger.error(f"Error stopping health server during shutdown: {e}")


if __name__ == "__main__":
    main()
