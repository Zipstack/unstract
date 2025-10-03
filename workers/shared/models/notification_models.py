"""Notification Data Models

This module provides strongly-typed dataclasses for notification operations,
replacing fragile dictionary-based notification handling with type-safe structures.
"""

# Import shared domain models from core
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../unstract/core/src"))


@dataclass
class NotificationRequest:
    """Strongly-typed notification request."""

    notification_type: str
    destination: str
    payload: dict[str, Any]
    priority: bool = False
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    headers: dict[str, str] | None = None
    metadata: dict[str, Any] | None = None
    organization_id: str | None = None
    workflow_id: str | None = None
    execution_id: str | None = None

    def __post_init__(self):
        """Validate notification request after initialization."""
        if not self.notification_type:
            raise ValueError("notification_type is required for notification request")

        if not self.destination:
            raise ValueError("destination is required for notification request")

        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dictionary")

        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")

    @property
    def is_high_priority(self) -> bool:
        """Check if this is a high priority notification."""
        return self.priority

    @property
    def is_webhook(self) -> bool:
        """Check if this is a webhook notification."""
        return self.notification_type.upper() == "WEBHOOK"

    @property
    def is_email(self) -> bool:
        """Check if this is an email notification."""
        return self.notification_type.upper() == "EMAIL"

    @property
    def is_sms(self) -> bool:
        """Check if this is an SMS notification."""
        return self.notification_type.upper() == "SMS"

    @property
    def payload_size(self) -> int:
        """Get the size of the payload in bytes."""
        import json

        return len(json.dumps(self.payload, default=str).encode("utf-8"))

    def get_header(self, header_name: str, default: str = "") -> str:
        """Get a header value."""
        if not self.headers:
            return default
        return self.headers.get(header_name, default)

    def set_header(self, header_name: str, header_value: str) -> None:
        """Set a header value."""
        if not self.headers:
            self.headers = {}
        self.headers[header_name] = header_value

    def to_dict(self) -> dict[str, Any]:
        """Convert notification request to dictionary."""
        result = {
            "notification_type": self.notification_type,
            "destination": self.destination,
            "payload": self.payload,
            "priority": self.priority,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
        }

        if self.headers:
            result["headers"] = self.headers

        if self.metadata:
            result["metadata"] = self.metadata

        if self.organization_id:
            result["organization_id"] = self.organization_id

        if self.workflow_id:
            result["workflow_id"] = self.workflow_id

        if self.execution_id:
            result["execution_id"] = self.execution_id

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotificationRequest":
        """Create NotificationRequest from dictionary data."""
        return cls(
            notification_type=data["notification_type"],
            destination=data["destination"],
            payload=data["payload"],
            priority=data.get("priority", False),
            timeout=data.get("timeout", 30),
            max_retries=data.get("max_retries", 3),
            retry_delay=data.get("retry_delay", 1.0),
            headers=data.get("headers"),
            metadata=data.get("metadata"),
            organization_id=data.get("organization_id"),
            workflow_id=data.get("workflow_id"),
            execution_id=data.get("execution_id"),
        )


@dataclass
class NotificationResult:
    """Strongly-typed result from notification delivery."""

    notification_id: str
    notification_type: str
    destination: str
    status: str
    success: bool
    delivery_time: float = 0.0
    attempts: int = 1
    response_code: int | None = None
    response_body: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None
    delivered_at: datetime | None = None

    def __post_init__(self):
        """Validate notification result after initialization."""
        if not self.notification_id:
            raise ValueError("notification_id is required for notification result")

        if not self.notification_type:
            raise ValueError("notification_type is required for notification result")

        if not self.destination:
            raise ValueError("destination is required for notification result")

        if not self.status:
            raise ValueError("status is required for notification result")

        # Set delivered_at if not provided and successful
        if self.delivered_at is None and self.success:
            self.delivered_at = datetime.now()

    @property
    def is_successful(self) -> bool:
        """Check if notification delivery was successful."""
        return self.success and self.status.upper() in [
            "SUCCESS",
            "DELIVERED",
            "COMPLETED",
        ]

    @property
    def is_failed(self) -> bool:
        """Check if notification delivery failed."""
        return not self.success or self.status.upper() in ["FAILED", "ERROR"]

    @property
    def is_pending(self) -> bool:
        """Check if notification is still pending."""
        return self.status.upper() in ["PENDING", "QUEUED", "PROCESSING"]

    @property
    def has_error(self) -> bool:
        """Check if notification has an error message."""
        return bool(self.error_message)

    @property
    def response_ok(self) -> bool:
        """Check if HTTP response was successful (2xx)."""
        if self.response_code is None:
            return False
        return 200 <= self.response_code < 300

    @property
    def delivery_time_ms(self) -> float:
        """Get delivery time in milliseconds."""
        return self.delivery_time * 1000

    def get_metadata_field(self, field_name: str, default: Any = None) -> Any:
        """Get a field from the metadata."""
        if not self.metadata:
            return default
        return self.metadata.get(field_name, default)

    def to_dict(self) -> dict[str, Any]:
        """Convert notification result to dictionary."""
        result = {
            "notification_id": self.notification_id,
            "notification_type": self.notification_type,
            "destination": self.destination,
            "status": self.status,
            "success": self.success,
            "delivery_time": self.delivery_time,
            "attempts": self.attempts,
        }

        if self.response_code is not None:
            result["response_code"] = self.response_code

        if self.response_body:
            result["response_body"] = self.response_body

        if self.error_message:
            result["error_message"] = self.error_message

        if self.metadata:
            result["metadata"] = self.metadata

        if self.delivered_at:
            result["delivered_at"] = self.delivered_at.isoformat()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotificationResult":
        """Create NotificationResult from dictionary data."""
        delivered_at = None
        if "delivered_at" in data and data["delivered_at"]:
            if isinstance(data["delivered_at"], str):
                delivered_at = datetime.fromisoformat(
                    data["delivered_at"].replace("Z", "+00:00")
                )
            elif isinstance(data["delivered_at"], datetime):
                delivered_at = data["delivered_at"]

        return cls(
            notification_id=data["notification_id"],
            notification_type=data["notification_type"],
            destination=data["destination"],
            status=data["status"],
            success=data["success"],
            delivery_time=data.get("delivery_time", 0.0),
            attempts=data.get("attempts", 1),
            response_code=data.get("response_code"),
            response_body=data.get("response_body"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata"),
            delivered_at=delivered_at,
        )


@dataclass
class WebhookNotificationRequest(NotificationRequest):
    """Specialized notification request for webhooks."""

    url: str = ""
    method: str = "POST"

    def __post_init__(self):
        """Validate webhook notification request."""
        # Set destination to URL for webhook requests
        if not self.destination and self.url:
            self.destination = self.url
        elif not self.url and self.destination:
            self.url = self.destination

        super().__post_init__()

        if not self.url:
            raise ValueError("url is required for webhook notification")

        if self.method.upper() not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            raise ValueError(f"Invalid HTTP method: {self.method}")

    @property
    def is_post_request(self) -> bool:
        """Check if this is a POST request."""
        return self.method.upper() == "POST"

    def to_dict(self) -> dict[str, Any]:
        """Convert webhook request to dictionary."""
        result = super().to_dict()
        result.update(
            {
                "url": self.url,
                "method": self.method,
            }
        )
        return result


@dataclass
class NotificationBatch:
    """Strongly-typed batch of notifications."""

    batch_id: str
    notifications: list[NotificationRequest] = field(default_factory=list)
    priority: bool = False
    created_at: datetime | None = None
    processed_at: datetime | None = None
    total_notifications: int = 0
    successful_notifications: int = 0
    failed_notifications: int = 0
    pending_notifications: int = 0
    batch_status: str = "PENDING"
    results: list[NotificationResult] = field(default_factory=list)

    def __post_init__(self):
        """Validate notification batch after initialization."""
        if not self.batch_id:
            raise ValueError("batch_id is required for notification batch")

        # Set created_at if not provided
        if self.created_at is None:
            self.created_at = datetime.now()

        # Auto-calculate total if not provided
        if self.total_notifications == 0:
            self.total_notifications = len(self.notifications)

    @property
    def completion_percentage(self) -> float:
        """Get completion percentage of the batch."""
        if self.total_notifications == 0:
            return 100.0
        processed = self.successful_notifications + self.failed_notifications
        return (processed / self.total_notifications) * 100.0

    @property
    def success_rate(self) -> float:
        """Get success rate of processed notifications."""
        processed = self.successful_notifications + self.failed_notifications
        if processed == 0:
            return 0.0
        return (self.successful_notifications / processed) * 100.0

    @property
    def is_completed(self) -> bool:
        """Check if batch processing is completed."""
        return self.batch_status.upper() == "COMPLETED"

    @property
    def is_failed(self) -> bool:
        """Check if batch processing failed."""
        return self.batch_status.upper() == "FAILED"

    @property
    def has_errors(self) -> bool:
        """Check if batch has any failed notifications."""
        return self.failed_notifications > 0

    def add_notification(self, notification: NotificationRequest) -> None:
        """Add a notification to the batch."""
        self.notifications.append(notification)
        self.total_notifications = len(self.notifications)

    def add_result(self, result: NotificationResult) -> None:
        """Add a notification result to the batch."""
        self.results.append(result)

        # Update counts
        if result.is_successful:
            self.successful_notifications += 1
        elif result.is_failed:
            self.failed_notifications += 1
        else:
            self.pending_notifications += 1

    def get_successful_results(self) -> list[NotificationResult]:
        """Get only the successful notification results."""
        return [r for r in self.results if r.is_successful]

    def get_failed_results(self) -> list[NotificationResult]:
        """Get only the failed notification results."""
        return [r for r in self.results if r.is_failed]

    def get_error_messages(self) -> list[str]:
        """Get all error messages from failed results."""
        return [r.error_message for r in self.results if r.error_message]

    def to_dict(self) -> dict[str, Any]:
        """Convert notification batch to dictionary."""
        result = {
            "batch_id": self.batch_id,
            "total_notifications": self.total_notifications,
            "successful_notifications": self.successful_notifications,
            "failed_notifications": self.failed_notifications,
            "pending_notifications": self.pending_notifications,
            "batch_status": self.batch_status,
            "priority": self.priority,
            "completion_percentage": self.completion_percentage,
            "success_rate": self.success_rate,
        }

        if self.notifications:
            result["notifications"] = [n.to_dict() for n in self.notifications]

        if self.results:
            result["results"] = [r.to_dict() for r in self.results]

        if self.created_at:
            result["created_at"] = self.created_at.isoformat()

        if self.processed_at:
            result["processed_at"] = self.processed_at.isoformat()

        return result


@dataclass
class NotificationTemplate:
    """Strongly-typed notification template."""

    template_id: str
    template_name: str
    notification_type: str
    template_content: str
    variables: list[str] = field(default_factory=list)
    default_headers: dict[str, str] | None = None
    default_timeout: int = 30
    default_retries: int = 3
    is_active: bool = True
    created_at: datetime | None = None

    def __post_init__(self):
        """Validate notification template after initialization."""
        if not self.template_id:
            raise ValueError("template_id is required for notification template")

        if not self.template_name:
            raise ValueError("template_name is required for notification template")

        if not self.notification_type:
            raise ValueError("notification_type is required for notification template")

        if not self.template_content:
            raise ValueError("template_content is required for notification template")

        # Set created_at if not provided
        if self.created_at is None:
            self.created_at = datetime.now()

    @property
    def has_variables(self) -> bool:
        """Check if template has variables."""
        return bool(self.variables)

    @property
    def variable_count(self) -> int:
        """Get the number of variables in the template."""
        return len(self.variables)

    def render(self, variables: dict[str, Any]) -> str:
        """Render the template with provided variables."""
        content = self.template_content

        for var_name in self.variables:
            if var_name in variables:
                placeholder = f"{{{var_name}}}"
                content = content.replace(placeholder, str(variables[var_name]))

        return content

    def create_notification_request(
        self, destination: str, variables: dict[str, Any] | None = None, **kwargs
    ) -> NotificationRequest:
        """Create a notification request from this template."""
        # Render template content
        rendered_content = self.render(variables or {})

        # Create base payload
        payload = {"content": rendered_content}
        if "payload" in kwargs:
            payload.update(kwargs.pop("payload"))

        return NotificationRequest(
            notification_type=self.notification_type,
            destination=destination,
            payload=payload,
            timeout=kwargs.get("timeout", self.default_timeout),
            max_retries=kwargs.get("max_retries", self.default_retries),
            headers=kwargs.get("headers", self.default_headers),
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert notification template to dictionary."""
        result = {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "notification_type": self.notification_type,
            "template_content": self.template_content,
            "variables": self.variables,
            "default_timeout": self.default_timeout,
            "default_retries": self.default_retries,
            "is_active": self.is_active,
        }

        if self.default_headers:
            result["default_headers"] = self.default_headers

        if self.created_at:
            result["created_at"] = self.created_at.isoformat()

        return result


# Utility functions for notification operations
def create_webhook_notification(
    url: str, payload: dict[str, Any], method: str = "POST", **kwargs
) -> WebhookNotificationRequest:
    """Create a webhook notification request."""
    return WebhookNotificationRequest(
        notification_type="WEBHOOK",
        url=url,
        method=method,
        destination=url,
        payload=payload,
        **kwargs,
    )


def create_notification_batch(
    notifications: list[NotificationRequest],
    batch_id: str | None = None,
    priority: bool = False,
) -> NotificationBatch:
    """Create a notification batch from a list of notifications."""
    import uuid

    if batch_id is None:
        batch_id = str(uuid.uuid4())

    return NotificationBatch(
        batch_id=batch_id,
        notifications=notifications,
        priority=priority,
    )


def aggregate_notification_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate multiple notification results into summary statistics."""
    total = len(results)
    successful = len([r for r in results if r.get("success", False)])
    failed = total - successful

    total_time = sum(r.get("delivery_time", 0.0) for r in results)
    avg_time = total_time / total if total > 0 else 0.0

    return {
        "total_notifications": total,
        "successful_notifications": successful,
        "failed_notifications": failed,
        "success_rate": (successful / total * 100) if total > 0 else 0.0,
        "total_delivery_time": total_time,
        "average_delivery_time": avg_time,
    }
