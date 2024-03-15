from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Optional

import redis


# class LogHelper:
#     logging.basicConfig(
#         level=logging.INFO,
#         format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
#     )

#     @staticmethod
#     def log(
#         stage: str,
#         message: str,
#         level: str = "INFO",
#         cost_type: str = None,
#         cost_units: str = None,
#         cost_value: float = None,
#         step: str = None,
#         iteration: int = None,
#         iteration_total: int = None,
#     ) -> dict:
#         return {
#             "_pandora_message_type": "log",
#             "level": level,
#             "stage": stage,
#             "message": message,
#             "cost_type": cost_type,
#             "cost_units": cost_units,
#             "cost_value": cost_value,
#             "step": step,
#             "iteration": iteration,
#             "iteration_total": iteration_total,
#         }

#     @staticmethod
#     def update(
#         component: str,
#         state: str,
#         state_message: str,
#     ) -> dict:
#         return {
#             "_pandora_message_type": "update",
#             "component": component,
#             "state": state,
#             "state_message": state_message,
#         }

#     @staticmethod
#     def publish(project_guid: str, message: dict) -> bool:
#         channel = f"logs:{project_guid}"
#         redis_host = os.environ.get("REDIS_HOST")
#         redis_port = os.environ.get("REDIS_PORT")

#         redis_user = os.environ.get("REDIS_USER")
#         redis_password = os.environ.get("REDIS_PASSWORD")

#         if not redis_host:
#             raise RuntimeError("REDIS_HOST environment variable not set")

#         if not redis_user:
#             raise RuntimeError("REDIS_USER environment variable not set")

#         if not redis_password:
#             redis_password = None

#         try:
#             r = redis.Redis(
#                 host=redis_host,
#                 port=int(redis_port),
#                 username=redis_user,
#                 password=redis_password,
#             )
#             payload = json.dumps(message)
#             r.publish(channel, payload)
#             r.close()
#         except Exception as e:
#             logging.error(f"Could not publish message to channel {channel}: {e}")
#             return False
#         return True


class LogPublisher:

    r = redis.Redis(
        host=os.environ.get("REDIS_HOST", "http://localhost"),
        port=os.environ.get("REDIS_PORT", "6379"),
        username=os.environ.get("REDIS_USER", ""),
        password=os.environ.get("REDIS_PASSWORD", ""),
    )

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
    ) -> dict[str, Any]:
        return {
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
        }

    @staticmethod
    def log_workflow_update(
        state: str,
        message: str,
        component: Optional[str],
    ) -> dict[str, Any]:
        return {
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

    @staticmethod
    def publish(channel_id: str, payload: dict[str, Any]) -> bool:
        channel = f"logs:{channel_id}"
        try:
            LogPublisher.r.publish(channel, json.dumps(payload))
        except Exception as e:
            logging.error(
                f"Failed to publish '{channel}' <= {payload}: {e}"
            )
            return False
        return True