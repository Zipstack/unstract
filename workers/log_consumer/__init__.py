"""Log Consumer Worker for Unstract Platform

This worker consumes log messages from the celery_log_task_queue and processes them
by storing to Redis and triggering WebSocket emissions through the backend API.
"""
