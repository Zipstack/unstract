# Quick Start: Task Abstraction Layer Migration

**Phase**: 1 - Design & Contracts  
**Date**: 2025-09-14  
**Prerequisites**: Task abstraction library implemented

## Overview

This quickstart guide demonstrates how to migrate from legacy services (Runner, Structure Tool, Prompt Service) to the unified task abstraction layer with multiple backend support.

## Prerequisites

- Python 3.12+
- Redis (for Celery backend)
- PostgreSQL (for Hatchet backend, optional)
- Flipt server (for feature flags)
- Docker and Docker Compose (for local development)

## 1. Installation and Setup

### Install Task Abstraction Library

```bash
# From project root
cd unstract/task-abstraction
uv sync --group dev

# Install with all backend support
pip install -e ".[hatchet,celery,temporal]"
```

### Environment Configuration

```bash
# backend/.env
TASK_QUEUE_BACKEND=celery  # Start with Celery backend
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Feature flags
FLIPT_SERVER_URL=http://localhost:8080
FLIPT_NAMESPACE=default

# Migration flags (start with false)
TASK_ABSTRACTION_ENABLED=false
HATCHET_BACKEND_ENABLED=false
PROMPT_HELPERS_ENABLED=false
```

## 2. Define Your First Workflow

Replace existing service calls with workflow definitions:

```python
# backend/workflows/document_processing.py
from unstract.task_abstraction import workflow, task, BaseWorkflow, TaskContext
from unstract.prompt_helpers import ExtractionHelper, LLMHelper

@workflow(
    name="document-processing-v2",
    description="Replace Runner → Structure Tool → Prompt Studio chain",
    timeout_minutes=30
)
class DocumentProcessingWorkflow(BaseWorkflow):
    
    @task(name="extract-text", timeout_minutes=10)
    def extract_text(self, input_data: dict, ctx: TaskContext) -> dict:
        """Replace Structure Tool with helper function."""
        extractor = ExtractionHelper()
        result = extractor.extract_text_from_file(input_data["document_path"])
        
        return {
            "text": result.extracted_text,
            "page_count": result.page_count,
            "extraction_method": result.extraction_method
        }
    
    @task(name="process-llm", parents=["extract-text"], timeout_minutes=15)  
    def process_llm(self, input_data: dict, ctx: TaskContext) -> dict:
        """Replace Prompt Studio service with helper."""
        text_data = ctx.task_output("extract-text")
        
        llm_helper = LLMHelper(
            adapter_instance_id=input_data["llm_adapter_id"]
        )
        
        processed_results = {}
        for output_config in input_data.get("outputs", []):
            result = llm_helper.process_prompt(
                output_config["prompt"],
                context={"text": text_data["text"]}
            )
            processed_results[output_config["name"]] = {
                "response": result.response,
                "tokens_used": result.tokens_used
            }
        
        return {"processed_results": processed_results}
```

## 3. Setup Migration Execution Manager

```python
# backend/workflow_manager/migration_manager.py
import os
from unstract.task_abstraction import get_task_client
from unstract.flags.feature_flag import check_feature_flag_status

class DocumentProcessingMigrationManager:
    """Manages migration between legacy and new systems."""
    
    def __init__(self):
        self.task_client = None
        
    async def process_document(self, input_data: dict, user_context: dict) -> dict:
        """Process document with migration support."""
        
        # Check feature flag
        use_abstraction = check_feature_flag_status(
            "task_abstraction_enabled",
            "default",
            user_context.get("user_id", "anonymous"),
            context=user_context
        )
        
        if use_abstraction:
            return await self._process_with_abstraction(input_data, user_context)
        else:
            return await self._process_legacy(input_data, user_context)
    
    async def _process_with_abstraction(self, input_data: dict, user_context: dict) -> dict:
        """Process using task abstraction layer."""
        if not self.task_client:
            self.task_client = get_task_client()
            await self.task_client.startup()
        
        # Execute workflow
        workflow_id = await self.task_client.run_workflow_async(
            "document-processing-v2",
            input_data
        )
        
        # Get result
        result = await self.task_client.get_workflow_result(workflow_id)
        
        return {
            "workflow_id": workflow_id,
            "status": result.status.value,
            "results": result.task_results,
            "backend_used": "task_abstraction"
        }
    
    async def _process_legacy(self, input_data: dict, user_context: dict) -> dict:
        """Process using legacy services."""
        # Legacy Runner Service call
        from backend.services.runner_service import RunnerService
        runner = RunnerService()
        
        result = await runner.process_document(input_data)
        
        return {
            "task_id": result.get("task_id"),
            "status": result.get("status"),
            "results": result.get("results"),
            "backend_used": "legacy_services"
        }
```

## 4. Update API Endpoints

```python
# backend/api_v2/workflow_execution_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .migration_manager import DocumentProcessingMigrationManager

class DocumentProcessingView(APIView):
    """Document processing with migration support."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.migration_manager = DocumentProcessingMigrationManager()
    
    async def post(self, request):
        """Process document with automatic migration."""
        input_data = request.data.get("input_data", {})
        user_context = {
            "user_id": request.user.id if request.user.is_authenticated else None,
            "organization_id": getattr(request.user, 'organization_id', None),
            "api_version": "v2"
        }
        
        try:
            result = await self.migration_manager.process_document(
                input_data, user_context
            )
            
            return Response(result, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": str(e), "fallback_available": True},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
```

## 5. Configure Feature Flags

### Flipt Configuration

```yaml
# flipt/flags.yml
namespace: default
flags:
  - key: task_abstraction_enabled
    name: "Task Abstraction Enabled"
    description: "Enable new task abstraction layer"
    enabled: true
    variants:
      - key: "0"
        name: "Disabled"
      - key: "25"
        name: "25% Rollout"
      - key: "50"
        name: "50% Rollout"
      - key: "100"
        name: "Fully Enabled"
    rules:
      - segment: beta_users
        distributions:
          - variant: "100"
            rollout: 100
      - segment: default
        distributions:
          - variant: "0"
            rollout: 75
          - variant: "25"
            rollout: 25

segments:
  - key: beta_users
    name: "Beta Users"
    match_type: ANY_MATCH_TYPE
    constraints:
      - type: STRING_COMPARISON_TYPE
        property: organization_id
        operator: EQ_COMPARISON_OPERATOR
        value: "beta_org"
```

### Start Flipt Server

```bash
# Start Flipt server
docker run -d \
  --name flipt \
  -p 8080:8080 \
  -v $(pwd)/flipt:/etc/flipt \
  flipt/flipt:latest
```

## 6. Register Workflows at Startup

```python
# backend/management/commands/register_workflows.py
from django.core.management.base import BaseCommand
from unstract.task_abstraction import get_task_client
from backend.workflows.document_processing import DocumentProcessingWorkflow

class Command(BaseCommand):
    help = 'Register workflows with task abstraction layer'
    
    async def handle(self, *args, **options):
        """Register all workflows."""
        
        # Get task client
        client = get_task_client()
        await client.startup()
        
        try:
            # Register document processing workflow
            workflow_def = DocumentProcessingWorkflow.get_workflow_definition()
            await client.register_workflow(workflow_def)
            
            self.stdout.write(
                self.style.SUCCESS(f'Registered workflow: {workflow_def.config.name}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to register workflows: {e}')
            )
        finally:
            await client.shutdown()
```

## 7. Testing Your Migration

### Test Legacy Behavior

```python
# Test with feature flag disabled
import asyncio
from backend.workflow_manager.migration_manager import DocumentProcessingMigrationManager

async def test_legacy():
    manager = DocumentProcessingMigrationManager()
    
    # Mock user context with feature flag disabled
    user_context = {"user_id": "test_user", "organization_id": "default"}
    input_data = {"document_path": "/test/document.pdf"}
    
    result = await manager.process_document(input_data, user_context)
    print(f"Backend used: {result['backend_used']}")  # Should be "legacy_services"

# Run test
asyncio.run(test_legacy())
```

### Test New Abstraction Layer

```bash
# Enable feature flag
curl -X PUT http://localhost:8080/api/v1/flags/task_abstraction_enabled \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

```python
async def test_abstraction():
    manager = DocumentProcessingMigrationManager()
    
    user_context = {"user_id": "test_user", "organization_id": "default"}
    input_data = {"document_path": "/test/document.pdf"}
    
    result = await manager.process_document(input_data, user_context)
    print(f"Backend used: {result['backend_used']}")  # Should be "task_abstraction"

asyncio.run(test_abstraction())
```

## 8. Monitor Migration Progress

```python
# backend/management/commands/migration_status.py
from django.core.management.base import BaseCommand
from backend.monitoring.migration_monitoring import MigrationMonitoringService

class Command(BaseCommand):
    help = 'Show migration status and metrics'
    
    def handle(self, *args, **options):
        monitoring = MigrationMonitoringService()
        dashboard = monitoring.get_migration_dashboard()
        
        self.stdout.write("=== Migration Dashboard ===")
        self.stdout.write(f"Total Executions: {dashboard['total_executions']}")
        
        for backend, percentage in dashboard['backend_distribution']['percentages'].items():
            self.stdout.write(f"{backend}: {percentage:.1f}%")
        
        self.stdout.write("\nSuccess Rates:")
        for backend, rate in dashboard['success_rates'].items():
            self.stdout.write(f"{backend}: {rate:.1f}%")
```

## 9. Gradual Rollout Process

### Phase 1: Internal Testing (0% → 5%)
```bash
# Update feature flag for beta users only
curl -X PUT http://localhost:8080/api/v1/flags/task_abstraction_enabled/variants \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "segment": "beta_users",
        "distributions": [{"variant": "100", "rollout": 100}]
      },
      {
        "segment": "default", 
        "distributions": [{"variant": "0", "rollout": 100}]
      }
    ]
  }'
```

### Phase 2: Gradual Rollout (5% → 50%)
```bash
# Increase rollout percentage
curl -X PUT http://localhost:8080/api/v1/flags/task_abstraction_enabled/variants \
  -d '{
    "rules": [
      {
        "segment": "default",
        "distributions": [
          {"variant": "0", "rollout": 50},
          {"variant": "100", "rollout": 50}
        ]
      }
    ]
  }'
```

### Phase 3: Full Migration (50% → 100%)
```bash
# Full rollout
curl -X PUT http://localhost:8080/api/v1/flags/task_abstraction_enabled/variants \
  -d '{
    "rules": [
      {
        "segment": "default",
        "distributions": [{"variant": "100", "rollout": 100}]
      }
    ]
  }'
```

## 10. Backend Migration (Celery → Hatchet)

Once task abstraction is fully deployed, migrate backends:

### Install Hatchet
```bash
# Add Hatchet to environment
echo "HATCHET_SERVER_URL=https://hatchet.unstract.localhost" >> backend/.env
echo "HATCHET_TOKEN=your_hatchet_token" >> backend/.env
```

### Enable Hatchet Backend
```bash
# Update environment
echo "TASK_QUEUE_BACKEND=hatchet" >> backend/.env

# Restart workers
docker-compose restart worker-unified
```

### Test Hatchet Integration
```python
async def test_hatchet():
    from unstract.task_abstraction import get_task_client
    
    # Get Hatchet client
    client = get_task_client(backend_override="hatchet")
    await client.startup()
    
    # Register workflow
    from backend.workflows.document_processing import DocumentProcessingWorkflow
    workflow_def = DocumentProcessingWorkflow.get_workflow_definition()
    await client.register_workflow(workflow_def)
    
    # Execute workflow
    result = await client.run_workflow_async(
        "document-processing-v2",
        {"document_path": "/test/doc.pdf"}
    )
    
    print(f"Hatchet workflow result: {result}")
    
    await client.shutdown()

asyncio.run(test_hatchet())
```

## Expected Results

After completing this quickstart:

✅ **Document processing workflows** execute through task abstraction layer  
✅ **Feature flags control** backend selection between legacy and new systems  
✅ **Gradual rollout** enables safe migration with immediate rollback capability  
✅ **Service consolidation** eliminates Runner, Structure Tool, and Prompt Service dependencies  
✅ **Multiple backend support** allows switching between Celery and Hatchet  
✅ **Monitoring and metrics** provide visibility into migration progress  

## Troubleshooting

### Common Issues

1. **Feature flag not working**: Check Flipt server connection and namespace configuration
2. **Workflow registration fails**: Verify backend client configuration and connectivity
3. **Task execution errors**: Check worker logs and backend-specific error handling
4. **Migration metrics missing**: Ensure monitoring service is configured and running

### Debug Commands

```bash
# Check feature flag status
python manage.py shell -c "
from unstract.flags.feature_flag import check_feature_flag_status
print(check_feature_flag_status('task_abstraction_enabled', 'default', 'test_user'))
"

# Test workflow registration
python manage.py register_workflows

# View migration dashboard
python manage.py migration_status

# Check backend connectivity
python -c "
import asyncio
from unstract.task_abstraction import get_task_client
async def test():
    client = get_task_client()
    await client.startup()
    print('Backend connected successfully')
    await client.shutdown()
asyncio.run(test())
"
```

This quickstart provides a complete migration path from legacy services to the unified task abstraction layer with gradual rollout and backend flexibility.