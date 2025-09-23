# Celery to Task Abstraction Migration Plan

## 🎯 **Migration Overview**

This document provides a concrete migration path from your current **multiple Celery backends anti-pattern** to the **unified task abstraction layer**, eliminating operational complexity while maintaining functionality.

## 📋 **Current State Analysis**

### **Services to Eliminate**
1. **Runner Service**: Spawns Structure Tool containers
2. **Structure Tool**: Processes documents via containers  
3. **Prompt Studio Service**: Flask-based LLM processing service

### **Current Celery Problems to Fix**
- **7 separate worker processes** running simultaneously
- **4+ separate Celery application instances**
- **Multiple queue configurations** with separate backends
- **Resource duplication** across worker types

## 🚀 **3-Phase Migration Strategy**

### **Phase 1: Immediate Celery Consolidation (Week 1)**

**Goal**: Fix the anti-pattern by consolidating to single Celery app

#### **1.1 Create Unified Celery Configuration**

```python
# backend/unified_celery_config.py
from kombu import Queue
from backend.celery_config import CeleryConfig as BaseCeleryConfig

class UnifiedCeleryConfig(BaseCeleryConfig):
    """Single Celery configuration replacing multiple backends."""
    
    task_queues = [
        Queue('default', routing_key='default'),
        Queue('file_processing', routing_key='file_processing'),
        Queue('api_processing', routing_key='api_processing'), 
        Queue('logging', routing_key='logging'),
        Queue('callbacks', routing_key='callbacks'),
    ]
    
    task_default_queue = 'default'
    
    task_routes = {
        # File processing tasks
        'workflow_manager.workflow_v2.file_execution_tasks.*': {
            'queue': 'file_processing'
        },
        
        # API deployment tasks  
        'api_v2.deployment_tasks.*': {
            'queue': 'api_processing'
        },
        
        # Callback tasks
        '*.callback*': {
            'queue': 'callbacks'
        },
        
        # Logging tasks
        'scheduler.tasks.*': {
            'queue': 'logging'
        },
    }
    
    # Optimize for mixed workloads
    worker_prefetch_multiplier = 1
    task_acks_late = True
    worker_max_tasks_per_child = 100
    
    # Import all task modules
    imports = [
        'workflow_manager.workflow_v2.file_execution_tasks',
        'api_v2.deployment_tasks',
        'scheduler.tasks',
        'notification_v2.tasks',
    ]
```

#### **1.2 Create Single Celery App**

```python
# backend/unified_celery.py
import os
from celery import Celery
from backend.unified_celery_config import UnifiedCeleryConfig

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings.dev')

# Single Celery app replacing all separate apps
app = Celery('unstract_unified')
app.config_from_object(UnifiedCeleryConfig)

# Auto-discover tasks from all Django apps
app.autodiscover_tasks()
```

#### **1.3 Update Docker Configuration**

```yaml
# docker/docker-compose.yaml - Replace multiple workers with unified workers
services:
  # Replace 7 workers with 2 optimized workers
  worker-unified:
    image: unstract/backend:${VERSION}
    container_name: unstract-worker-unified
    restart: unless-stopped
    entrypoint: .venv/bin/celery
    command: >
      -A backend.unified_celery worker 
      --loglevel=info 
      --queues=default,file_processing,api_processing,callbacks
      --autoscale=8,2
      --max-tasks-per-child=100
      --prefetch-multiplier=1
    env_file:
      - ../backend/.env
    depends_on:
      - rabbitmq
      - db
    volumes:
      - ./workflow_data:/data
      - ${TOOL_REGISTRY_CONFIG_SRC_PATH}:/data/tool_registry_config

  # Optional: Specialized worker for heavy processing
  worker-heavy:  
    image: unstract/backend:${VERSION}
    container_name: unstract-worker-heavy
    restart: unless-stopped
    entrypoint: .venv/bin/celery
    command: >
      -A backend.unified_celery worker
      --loglevel=info
      --queues=file_processing
      --autoscale=4,1
      --max-memory-per-child=2048000
    env_file:
      - ../backend/.env
    depends_on:
      - rabbitmq
      - db
    volumes:
      - ./workflow_data:/data
      - ${TOOL_REGISTRY_CONFIG_SRC_PATH}:/data/tool_registry_config

  # Remove these containers:
  # worker-logging:
  # worker-file-processing:
  # worker-file-processing-callback:
```

#### **1.4 Validate Phase 1**

```bash
# Test unified worker setup
cd backend
poe unified-worker  # New task in pyproject.toml

# Verify all queues are working
celery -A backend.unified_celery inspect active_queues

# Monitor with single Flower instance
celery -A backend.unified_celery flower
```

**Expected Results**:
- Reduce from **7 workers to 2 workers**
- **60% reduction in memory usage**
- All existing functionality maintained

---

### **Phase 2: Task Abstraction Integration (Week 2-3)**

**Goal**: Introduce abstraction layer alongside existing Celery

#### **2.1 Install Task Abstraction Package**

```bash
# Add to backend dependencies
cd backend
uv add "../unstract/task-abstraction[hatchet,celery]"
```

#### **2.2 Create Workflow Definitions**

Replace complex Celery chains with workflow definitions:

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
        # Instead of: runner.spawn_structure_tool(file_path)
        # Use: Direct helper function call
        extractor = ExtractionHelper()
        result = extractor.extract_text_from_file(input_data["document_path"])
        
        return {
            "text": result.extracted_text,
            "page_count": result.page_count,
            "extraction_method": result.extraction_method
        }
    
    @task(name="chunk-text", parents=["extract-text"], timeout_minutes=5)
    def chunk_text(self, input_data: dict, ctx: TaskContext) -> dict:
        """Chunk extracted text."""
        text_data = ctx.task_output("extract-text")
        
        chunking_helper = ChunkingHelper()
        result = chunking_helper.chunk_text(text_data["text"])
        
        return {
            "chunks": result.chunks,
            "total_chunks": result.chunk_count
        }
    
    @task(name="process-llm", parents=["chunk-text"], timeout_minutes=15)  
    def process_llm(self, input_data: dict, ctx: TaskContext) -> dict:
        """Replace Prompt Studio service with helper."""
        chunks_data = ctx.task_output("chunk-text")
        
        # Instead of: requests.post("http://prompt-service/api/process", data)
        # Use: Direct helper function call
        llm_helper = LLMHelper(
            adapter_instance_id=input_data["llm_adapter_id"]
        )
        
        processed_results = {}
        for output_config in input_data.get("outputs", []):
            chunk_results = []
            for chunk in chunks_data["chunks"]:
                result = llm_helper.process_prompt(
                    output_config["prompt"],
                    context={"text": chunk}
                )
                chunk_results.append({
                    "response": result.response,
                    "tokens_used": result.tokens_used
                })
            
            processed_results[output_config["name"]] = chunk_results
        
        return {"processed_results": processed_results}
```

#### **2.3 Create Dual-Mode Execution**

Support both Celery and abstraction layer during migration:

```python
# backend/workflow_manager/execution_manager.py
import os
from typing import Dict, Any, Optional
from unstract.task_abstraction import get_task_client

class ExecutionManager:
    """Manages task execution with dual backend support."""
    
    def __init__(self):
        self.use_abstraction = os.getenv('USE_TASK_ABSTRACTION', 'false').lower() == 'true'
    
    async def execute_document_processing(
        self, 
        input_data: Dict[str, Any],
        workflow_endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute document processing via abstraction or legacy Celery."""
        
        if self.use_abstraction:
            # Use new abstraction layer
            client = get_task_client()
            if not client.is_started:
                await client.startup()
            
            result = await client.run_workflow(
                "document-processing-v2", 
                input_data
            )
            
            return {
                "workflow_id": result.workflow_id,
                "status": result.status.value,
                "results": result.task_results
            }
        
        else:
            # Fall back to legacy Celery chain
            return await self._execute_legacy_celery(input_data)
    
    async def _execute_legacy_celery(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute via consolidated Celery (Phase 1)."""
        from backend.unified_celery import app as celery_app
        
        # Use consolidated Celery instead of multiple apps
        result = celery_app.send_task(
            'workflow_manager.workflow_v2.file_execution_tasks.process_file',
            args=[input_data],
            queue='file_processing'
        )
        
        return {"task_id": result.id, "status": "submitted"}
```

#### **2.4 Update API Endpoints**

```python
# backend/api_v2/workflow_execution_views.py
from workflow_manager.execution_manager import ExecutionManager

class WorkflowExecutionView(APIView):
    async def post(self, request):
        """Execute workflow with dual backend support."""
        execution_manager = ExecutionManager()
        
        result = await execution_manager.execute_document_processing(
            input_data=request.data
        )
        
        return Response(result, status=status.HTTP_200_OK)
```

---

### **Phase 3: Complete Migration (Week 4-5)**

**Goal**: Complete migration to abstraction layer, eliminate legacy systems

#### **3.1 Switch to Abstraction Layer**

```bash
# Update environment configuration
echo "USE_TASK_ABSTRACTION=true" >> backend/.env
echo "TASK_QUEUE_BACKEND=hatchet" >> backend/.env
```

#### **3.2 Remove Legacy Services**

Update docker-compose to remove eliminated services:

```yaml
# docker/docker-compose.yaml - Remove eliminated services
services:
  # Remove these services completely:
  # runner:           # Eliminated - functionality moved to workflows
  # prompt-service:   # Eliminated - functionality moved to helpers
  
  # Keep but update these:
  backend:
    # Remove dependencies on eliminated services
    depends_on:
      - db
      - redis
      - rabbitmq
      - reverse-proxy
      - minio
      - minio-bootstrap
      - platform-service
      # - prompt-service    # REMOVED
      - x2text-service
  
  # Replace Celery workers with Hatchet worker
  hatchet-worker:
    image: unstract/backend:${VERSION}
    container_name: unstract-hatchet-worker
    restart: unless-stopped
    command: python -m backend.start_hatchet_worker
    env_file:
      - ../backend/.env
    depends_on:
      - db
      - redis
    volumes:
      - ./workflow_data:/data
      - ${TOOL_REGISTRY_CONFIG_SRC_PATH}:/data/tool_registry_config
```

#### **3.3 Create Hatchet Worker Startup**

```python
# backend/start_hatchet_worker.py
import asyncio
import logging
from unstract.task_abstraction import get_task_client
from backend.workflows.document_processing import DocumentProcessingWorkflow

logger = logging.getLogger(__name__)

async def start_hatchet_worker():
    """Start Hatchet worker with all workflows."""
    logger.info("Starting Hatchet worker...")
    
    # Get task client (Hatchet)
    client = get_task_client()
    
    # Register all workflows
    await client.register_workflow(DocumentProcessingWorkflow)
    
    # Start worker
    await client.startup()
    logger.info("Hatchet worker started successfully")
    
    # Keep worker running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down Hatchet worker...")
        await client.shutdown()

if __name__ == "__main__":
    asyncio.run(start_hatchet_worker())
```

## 📊 **Migration Validation**

### **Phase 1 Validation (Consolidated Celery)**

```bash
# Verify container reduction
docker ps | grep unstract-worker | wc -l  # Should show 2 instead of 7

# Memory usage comparison
docker stats --no-stream | grep unstract-worker

# Test all task types
celery -A backend.unified_celery inspect active_queues
```

### **Phase 2 Validation (Dual Mode)**

```bash
# Test abstraction layer
curl -X POST http://localhost:8000/api/v2/workflows/execute \
  -H "Content-Type: application/json" \
  -d '{"document_path": "/test/doc.pdf", "use_abstraction": true}'

# Test legacy path  
curl -X POST http://localhost:8000/api/v2/workflows/execute \
  -H "Content-Type: application/json" \
  -d '{"document_path": "/test/doc.pdf", "use_abstraction": false}'
```

### **Phase 3 Validation (Complete Migration)**

```bash
# Verify service elimination
docker ps | grep -E "runner|prompt-service"  # Should return empty

# Test workflow execution
curl -X POST http://localhost:8000/api/v2/workflows/execute \
  -H "Content-Type: application/json" \
  -d '{"document_path": "/test/doc.pdf"}'

# Monitor Hatchet execution
docker logs unstract-hatchet-worker
```

## 🎯 **Expected Outcomes**

### **Resource Savings**
- **Container Count**: 7+ → 1-2 (80%+ reduction)
- **Memory Usage**: ~2GB → ~500MB (75% reduction)  
- **Service Count**: 3 services eliminated (Runner, Structure Tool, Prompt Studio)

### **Operational Benefits**
- **Simplified Deployment**: Single workflow orchestration system
- **Better Debugging**: Unified execution tracing
- **Improved Scaling**: Smart resource allocation across task types
- **Reduced Complexity**: One configuration instead of multiple backend configs

### **Architectural Improvements**
- **Service Consolidation**: 3 fewer services to maintain
- **Workflow Orchestration**: Proper DAG execution with dependencies
- **Helper Function Approach**: Decoupled, testable business logic
- **Future-Proof**: Easy to switch orchestration backends

## ✅ **Success Criteria**

- [ ] **Phase 1**: Reduce worker containers from 7 to 2
- [ ] **Phase 1**: All existing Celery tasks work with unified app
- [ ] **Phase 2**: Abstraction layer executes workflows successfully  
- [ ] **Phase 2**: Dual-mode execution works (abstraction + legacy)
- [ ] **Phase 3**: All 3 services eliminated (Runner, Structure Tool, Prompt Studio)
- [ ] **Phase 3**: Complete workflow execution via Hatchet
- [ ] **Final**: 75%+ reduction in resource usage achieved

This migration plan transforms your problematic multiple-backend Celery setup into a modern, unified workflow orchestration system while eliminating unnecessary services and complexity.