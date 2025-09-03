"""Integration Tests for Internal API
Tests for internal service APIs including authentication, workflow execution, and webhooks.
"""

from unittest.mock import MagicMock, patch

from account_v2.models import Organization, User
from django.conf import settings
from django.test import override_settings
from notification_v2.enums import AuthorizationType, NotificationType, PlatformType
from notification_v2.models import Notification
from rest_framework import status
from rest_framework.test import APITestCase
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution


class InternalAPIAuthenticationTestCase(APITestCase):
    """Test internal API authentication middleware."""

    def setUp(self):
        self.internal_api_key = "test-internal-api-key"
        self.organization = Organization.objects.create(display_name="Test Organization")

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_health_endpoint_with_valid_api_key(self):
        """Test health endpoint with valid internal API key."""
        url = "/internal/api/v1/health/"
        headers = {
            "HTTP_AUTHORIZATION": f"Bearer {self.internal_api_key}",
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }

        response = self.client.get(url, **headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "healthy")
        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.data["organization_id"], str(self.organization.id))

    def test_health_endpoint_without_api_key(self):
        """Test health endpoint without API key should fail."""
        url = "/internal/api/v1/health/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn(
            "Authorization header with Bearer token required", response.data["error"]
        )

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_health_endpoint_with_invalid_api_key(self):
        """Test health endpoint with invalid API key should fail."""
        url = "/internal/api/v1/health/"
        headers = {"HTTP_AUTHORIZATION": "Bearer invalid-key"}

        response = self.client.get(url, **headers)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("Invalid internal service API key", response.data["error"])

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_api_root_documentation(self):
        """Test API root returns comprehensive documentation."""
        url = "/internal/api/"
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.internal_api_key}"}

        response = self.client.get(url, **headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("endpoints", response.data)
        self.assertIn("authentication", response.data)
        self.assertIn("workflow_execution_list", response.data["endpoints"]["v1"])
        self.assertIn("webhook_send", response.data["endpoints"]["v1"])


class WorkflowExecutionInternalAPITestCase(APITestCase):
    """Test workflow execution internal API endpoints."""

    def setUp(self):
        self.internal_api_key = "test-internal-api-key"
        self.organization = Organization.objects.create(display_name="Test Organization")
        self.user = User.objects.create(
            username="testuser", organization=self.organization
        )

        # Create test workflow execution
        self.workflow_execution = WorkflowExecution.objects.create(
            execution_mode=WorkflowExecution.Mode.INSTANT,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.PENDING,
            organization=self.organization,
        )

        self.headers = {
            "HTTP_AUTHORIZATION": f"Bearer {self.internal_api_key}",
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_get_workflow_execution_detail(self):
        """Test retrieving workflow execution details."""
        url = f"/internal/api/v1/workflow-execution/{self.workflow_execution.id}/"

        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("execution", response.data)
        self.assertEqual(
            response.data["execution"]["id"], str(self.workflow_execution.id)
        )
        self.assertIn("workflow_definition", response.data)
        self.assertIn("organization_context", response.data)

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_update_workflow_execution_status(self):
        """Test updating workflow execution status."""
        url = f"/internal/api/v1/workflow-execution/{self.workflow_execution.id}/update_status/"
        data = {
            "status": ExecutionStatus.EXECUTING.value,
            "total_files": 5,
            "attempts": 1,
        }

        response = self.client.post(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "updated")
        self.assertEqual(response.data["new_status"], ExecutionStatus.EXECUTING.value)

        # Verify database update
        self.workflow_execution.refresh_from_db()
        self.assertEqual(self.workflow_execution.status, ExecutionStatus.EXECUTING.value)
        self.assertEqual(self.workflow_execution.total_files, 5)

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_create_file_batch(self):
        """Test creating file batch for workflow execution."""
        url = "/internal/api/v1/workflow-execution/create-file-batch/"
        data = {
            "workflow_execution_id": str(self.workflow_execution.id),
            "is_api": False,
            "files": [
                {
                    "file_name": "test1.pdf",
                    "file_path": "/path/to/test1.pdf",
                    "file_size": 1024,
                    "file_hash": "abc123",
                    "mime_type": "application/pdf",
                },
                {
                    "file_name": "test2.pdf",
                    "file_path": "/path/to/test2.pdf",
                    "file_size": 2048,
                    "file_hash": "def456",
                    "mime_type": "application/pdf",
                },
            ],
        }

        response = self.client.post(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("batch_id", response.data)
        self.assertEqual(response.data["total_files"], 2)
        self.assertEqual(len(response.data["created_file_executions"]), 2)

        # Verify file executions were created
        file_executions = WorkflowFileExecution.objects.filter(
            workflow_execution=self.workflow_execution
        )
        self.assertEqual(file_executions.count(), 2)


class WebhookInternalAPITestCase(APITestCase):
    """Test webhook internal API endpoints."""

    def setUp(self):
        self.internal_api_key = "test-internal-api-key"
        self.organization = Organization.objects.create(display_name="Test Organization")

        # Create test notification
        self.notification = Notification.objects.create(
            name="Test Webhook",
            url="https://example.com/webhook",
            authorization_type=AuthorizationType.BEARER.value,
            authorization_key="test-token",
            max_retries=3,
            notification_type=NotificationType.WEBHOOK.value,
            platform=PlatformType.GENERIC.value,
            organization=self.organization,
        )

        self.headers = {
            "HTTP_AUTHORIZATION": f"Bearer {self.internal_api_key}",
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id),
        }

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_list_webhooks(self):
        """Test listing webhook configurations."""
        url = "/internal/api/v1/webhook/"

        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("notifications", response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["notifications"][0]["id"], str(self.notification.id)
        )

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    def test_get_webhook_configuration(self):
        """Test retrieving webhook configuration."""
        url = f"/internal/api/v1/webhook/{self.notification.id}/configuration/"

        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["notification_id"], str(self.notification.id))
        self.assertEqual(response.data["url"], self.notification.url)
        self.assertEqual(
            response.data["authorization_type"], self.notification.authorization_type
        )

    @override_settings(INTERNAL_SERVICE_API_KEY="test-internal-api-key")
    @patch("internal_api.webhook_views.send_webhook_notification.delay")
    def test_send_webhook_notification(self, mock_task):
        """Test sending webhook notification."""
        mock_task.return_value = MagicMock(id="test-task-123")

        url = "/internal/api/v1/webhook/send/"
        data = {
            "notification_id": str(self.notification.id),
            "url": "https://example.com/webhook",
            "payload": {"message": "Test notification"},
            "authorization_type": AuthorizationType.BEARER.value,
            "authorization_key": "test-token",
            "max_retries": 3,
            "retry_delay": 10,
        }

        response = self.client.post(url, data, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["task_id"], "test-task-123")
        self.assertEqual(response.data["status"], "queued")
        self.assertEqual(response.data["url"], data["url"])

        # Verify task was called
        mock_task.assert_called_once()


if __name__ == "__main__":
    import django

    django.setup()

    # Run tests
    from django.conf import settings
    from django.test.utils import get_runner

    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["internal_api.tests"])

    if failures:
        exit(1)
