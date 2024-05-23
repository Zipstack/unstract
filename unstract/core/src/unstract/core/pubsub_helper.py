import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import redis


class LogPublisher:
    r = redis.Redis(
        host=os.environ.get("REDIS_HOST", "http://localhost"),
        port=os.environ.get("REDIS_PORT", "6379"),
        username=os.environ.get("REDIS_USER", ""),
        password=os.environ.get("REDIS_PASSWORD", ""),
    )

    @staticmethod
    def log_usage(
        level: str = "INFO",
        added_token_count: Optional[int] = None,
        max_token_count_set: Optional[int] = None,
        enabled: bool = False,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "LOG",
            "service": "usage",
            "level": level,
            "added_token_count": added_token_count,
            "max_token_count_set": max_token_count_set,
            "enabled": enabled,
        }

    @staticmethod
    def log_workflow(
        stage: str,
        message: str,
        level: str = "INFO",
        cost_type: Optional[str] = None,
        cost_units: Optional[str] = None,
        cost_value: Optional[float] = None,
        step: Optional[int] = None,
        iteration: Optional[int] = None,
        iteration_total: Optional[int] = None,
        execution_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "LOG",
            "level": level,
            "stage": stage,
            "log": message,
            "cost_type": cost_type,
            "cost_units": cost_units,
            "cost_value": cost_value,
            "step": step,
            "iteration": iteration,
            "iteration_total": iteration_total,
            "execution_id": execution_id,
            "organization_id": organization_id,
        }

    @staticmethod
    def log_workflow_update(
        state: str,
        message: str,
        component: Optional[str],
    ) -> dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "UPDATE",
            "component": component,
            "state": state,
            "message": message,
        }

    @staticmethod
    def log_prompt(
        component: dict[str, str],
        level: str,
        state: str,
        message: str,
    ) -> dict[str, str]:
        return {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "type": "LOG",
            "service": "prompt",
            "component": component,
            "level": level,
            "state": state,
            "message": message,
        }

    @classmethod
    def publish(cls, channel_id: str, payload: dict[str, Any]) -> bool:
        channel = f"logs:{channel_id}"
        try:
            cls.r.publish(channel, json.dumps(payload))
        except Exception as e:
            logging.error(f"Failed to publish '{channel}' <= {payload}: {e}")
            return False
        return True
