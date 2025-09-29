"""Example Django backend integration for workflow registration.

This shows how to integrate workflows into the Django backend service,
particularly for user management, connector operations, and pipeline orchestration.
"""

import logging
from typing import Optional

from django.apps import AppConfig
from django.conf import settings

from unstract.task_abstraction import (
    workflow,
    task,
    BaseWorkflow,
    TaskContext
)
from unstract.task_abstraction.registry import register_django_workflows

logger = logging.getLogger(__name__)

# Backend workflow examples
@workflow(
    name="user-onboarding",
    description="User onboarding and setup workflow",
    timeout_minutes=15
)
class UserOnboardingWorkflow(BaseWorkflow):
    """User onboarding workflow for new account setup."""
    
    @task(name="create-user-account", timeout_minutes=2)
    def create_user_account(self, input_data: dict, ctx: TaskContext) -> dict:
        """Create user account in Django."""
        from django.contrib.auth.models import User
        from backend.account_v2.models import Organization
        
        user_data = input_data.get("user_data", {})
        email = user_data.get("email")
        
        # Create Django user
        user, created = User.objects.get_or_create(
            username=email,
            defaults={
                "email": email,
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
            }
        )
        
        return {
            "user_id": user.id,
            "created": created,
            "username": user.username
        }
    
    @task(name="setup-organization", parents=["create-user-account"])
    def setup_organization(self, input_data: dict, ctx: TaskContext) -> dict:
        """Setup organization for user."""
        from backend.account_v2.models import Organization
        
        user_data = ctx.task_output("create-user-account")
        org_data = input_data.get("organization", {})
        
        org = Organization.objects.create(
            name=org_data.get("name", f"Org for user {user_data['user_id']}"),
            created_by_id=user_data["user_id"]
        )
        
        return {
            "organization_id": org.id,
            "organization_name": org.name
        }
    
    @task(name="configure-defaults", parents=["setup-organization"])
    def configure_defaults(self, input_data: dict, ctx: TaskContext) -> dict:
        """Configure default settings for user."""
        user_data = ctx.task_output("create-user-account")
        org_data = ctx.task_output("setup-organization")
        
        # Set up default adapters, connectors, etc.
        defaults = {
            "default_llm_adapter": "openai_gpt35",
            "default_embedding_adapter": "openai_ada002",
            "trial_credits": 1000
        }
        
        return {
            "user_id": user_data["user_id"],
            "organization_id": org_data["organization_id"],
            "defaults_configured": defaults
        }


@workflow(
    name="connector-validation",
    description="Database connector validation and testing",
    timeout_minutes=10
)
class ConnectorValidationWorkflow(BaseWorkflow):
    """Workflow for validating database connectors."""
    
    @task(name="validate-credentials", timeout_minutes=3)
    def validate_credentials(self, input_data: dict, ctx: TaskContext) -> dict:
        """Validate connector credentials."""
        from backend.connector_v2.models import ConnectorInstance
        
        connector_id = input_data.get("connector_id")
        connector = ConnectorInstance.objects.get(id=connector_id)
        
        # Test connection (use existing connector logic)
        try:
            # This would use existing connector validation code
            connection_test = True  # Placeholder
            
            return {
                "connector_id": connector_id,
                "validation_status": "passed" if connection_test else "failed",
                "connection_details": {
                    "host": connector.connector_settings.get("host", ""),
                    "database": connector.connector_settings.get("database", "")
                }
            }
        except Exception as e:
            return {
                "connector_id": connector_id,
                "validation_status": "failed",
                "error": str(e)
            }
    
    @task(name="test-queries", parents=["validate-credentials"])
    def test_queries(self, input_data: dict, ctx: TaskContext) -> dict:
        """Test sample queries against connector."""
        validation_data = ctx.task_output("validate-credentials")
        
        if validation_data["validation_status"] != "passed":
            return {
                "query_test_status": "skipped",
                "reason": "Credential validation failed"
            }
        
        # Run test queries
        test_queries = [
            "SELECT 1",
            "SELECT COUNT(*) FROM information_schema.tables",
        ]
        
        query_results = []
        for query in test_queries:
            # Execute test query (use existing connector execution logic)
            result = {"query": query, "status": "success", "row_count": 1}
            query_results.append(result)
        
        return {
            "query_test_status": "passed",
            "test_results": query_results,
            "total_queries": len(test_queries)
        }


@workflow(
    name="pipeline-deployment",
    description="Deploy and activate extraction pipeline",
    timeout_minutes=20
)
class PipelineDeploymentWorkflow(BaseWorkflow):
    """Workflow for deploying extraction pipelines."""
    
    @task(name="validate-pipeline-config")
    def validate_pipeline_config(self, input_data: dict, ctx: TaskContext) -> dict:
        """Validate pipeline configuration."""
        from backend.pipeline.models import Pipeline
        
        pipeline_id = input_data.get("pipeline_id")
        pipeline = Pipeline.objects.get(id=pipeline_id)
        
        # Validate configuration
        validation_errors = []
        
        if not pipeline.prompt_studio_config:
            validation_errors.append("Prompt Studio configuration missing")
        
        if not pipeline.source_settings:
            validation_errors.append("Source settings missing")
        
        return {
            "pipeline_id": pipeline_id,
            "validation_status": "passed" if not validation_errors else "failed",
            "errors": validation_errors
        }
    
    @task(name="deploy-to-runner", parents=["validate-pipeline-config"])
    def deploy_to_runner(self, input_data: dict, ctx: TaskContext) -> dict:
        """Deploy pipeline to runner service."""
        validation_data = ctx.task_output("validate-pipeline-config")
        
        if validation_data["validation_status"] != "passed":
            return {
                "deployment_status": "failed",
                "reason": "Pipeline validation failed"
            }
        
        pipeline_id = validation_data["pipeline_id"]
        
        # Deploy to runner service (use existing deployment logic)
        deployment_result = {
            "pipeline_id": pipeline_id,
            "runner_endpoint": "http://runner.unstract.localhost:8000",
            "deployment_id": f"deploy_{ctx.workflow_id}",
            "status": "deployed"
        }
        
        return deployment_result
    
    @task(name="activate-pipeline", parents=["deploy-to-runner"])
    def activate_pipeline(self, input_data: dict, ctx: TaskContext) -> dict:
        """Activate deployed pipeline."""
        from backend.pipeline.models import Pipeline
        
        deployment_data = ctx.task_output("deploy-to-runner")
        pipeline_id = deployment_data["pipeline_id"]
        
        # Update pipeline status
        pipeline = Pipeline.objects.get(id=pipeline_id)
        pipeline.is_active = True
        pipeline.deployment_id = deployment_data["deployment_id"]
        pipeline.save()
        
        return {
            "pipeline_id": pipeline_id,
            "activation_status": "active",
            "deployment_id": deployment_data["deployment_id"]
        }


# Django app configuration
class WorkflowManagerConfig(AppConfig):
    """Django app config with workflow registration."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backend.workflow_manager'
    verbose_name = 'Workflow Manager'
    
    def ready(self):
        """Register workflows when Django app is ready."""
        # Only register in production or when explicitly enabled
        if settings.REGISTER_WORKFLOWS_ON_STARTUP:
            self._register_workflows()
    
    def _register_workflows(self):
        """Register Django workflows."""
        import asyncio
        from unstract.task_abstraction.registry import register_service_workflows
        
        async def _async_register():
            try:
                await register_service_workflows(
                    service_name="django-backend",
                    workflow_packages=[
                        "backend.workflows",
                        "backend.workflow_manager.workflows"
                    ]
                )
                logger.info("Django workflows registered successfully")
            except Exception as e:
                logger.error(f"Failed to register Django workflows: {e}")
        
        # Register workflows in background to avoid blocking Django startup
        try:
            asyncio.create_task(_async_register())
        except RuntimeError:
            # No event loop, skip for now
            logger.info("No event loop available, workflows will be registered on first use")


# Django management command for workflow operations
from django.core.management.base import BaseCommand
import asyncio

class Command(BaseCommand):
    """Django management command for workflow operations.
    
    Usage:
        python manage.py workflow_registry --register
        python manage.py workflow_registry --test --workflow user-onboarding
        python manage.py workflow_registry --status
    """
    
    help = 'Manage workflow registry for Django backend'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--register',
            action='store_true',
            help='Register all backend workflows'
        )
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test workflow execution'
        )
        parser.add_argument(
            '--workflow',
            type=str,
            help='Specific workflow name for testing'
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show workflow registration status'
        )
        parser.add_argument(
            '--backend',
            type=str,
            help='Task queue backend override'
        )
    
    def handle(self, *args, **options):
        """Handle management command."""
        asyncio.run(self._async_handle(options))
    
    async def _async_handle(self, options):
        """Async command handler."""
        from unstract.task_abstraction import get_task_client
        from unstract.task_abstraction.registry import register_service_workflows
        
        if options['register']:
            self.stdout.write("Registering Django backend workflows...")
            summary = await register_service_workflows(
                service_name="django-backend",
                workflow_packages=["backend.workflows"]
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Registration complete: {summary['registered']} workflows registered"
                )
            )
        
        elif options['test']:
            workflow_name = options.get('workflow', 'user-onboarding')
            self.stdout.write(f"Testing workflow: {workflow_name}")
            
            client = get_task_client(backend_override=options.get('backend'))
            await client.startup()
            
            # Test data
            test_data = {
                "user_data": {
                    "email": "test@example.com",
                    "first_name": "Test",
                    "last_name": "User"
                },
                "organization": {
                    "name": "Test Organization"
                }
            }
            
            result = await client.run_workflow(workflow_name, test_data)
            self.stdout.write(
                self.style.SUCCESS(f"Test completed with status: {result.status}")
            )
        
        elif options['status']:
            client = get_task_client(backend_override=options.get('backend'))
            workflows = client.get_registered_workflows()
            
            self.stdout.write(f"Registered workflows: {len(workflows)}")
            for name in workflows:
                self.stdout.write(f"  - {name}")


# Django view integration example
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import asyncio

@csrf_exempt
@require_http_methods(["POST"])
def create_user_workflow_view(request):
    """Django view that uses workflow abstraction."""
    
    async def _async_view():
        from unstract.task_abstraction import get_task_client
        
        # Parse request data
        data = json.loads(request.body)
        
        # Get task client
        client = get_task_client()
        if not client.is_started:
            await client.startup()
        
        # Execute user onboarding workflow
        result = await client.run_workflow("user-onboarding", data)
        
        return JsonResponse({
            "workflow_id": result.workflow_id,
            "status": result.status.value,
            "user_created": result.task_results.get("create-user-account", {}).get("result", {})
        })
    
    # Run async view (in production, use proper async Django views)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_view())
    finally:
        loop.close()


# Settings configuration
WORKFLOW_SETTINGS = {
    # Enable workflow registration during Django startup
    'REGISTER_WORKFLOWS_ON_STARTUP': True,
    
    # Default backend for Django workflows
    'DEFAULT_TASK_BACKEND': 'hatchet',
    
    # Workflow packages to auto-register
    'WORKFLOW_PACKAGES': [
        'backend.workflows',
        'backend.workflow_manager.workflows',
        'backend.pipeline.workflows',
    ],
    
    # Backend-specific settings
    'TASK_QUEUE_BACKEND': 'hatchet',  # or 'celery' for gradual migration
    'HATCHET_SERVER_URL': 'https://hatchet.unstract.localhost',
    'HATCHET_TOKEN': 'your-hatchet-token',
}