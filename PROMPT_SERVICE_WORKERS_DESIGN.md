# Prompt Service Workers: Django-Free Architecture with Enterprise Plugin Support

## Overview

This document outlines the design for moving prompt service to Django-free Celery workers, aligning with UN-2470 (remove Django dependency from Celery workers) while supporting enterprise plugin integration and minimal worker imports.

## Current State Analysis (UN-2470)

### Existing Worker Issues
```python
# Current problematic pattern in backend/workers/
from django.conf import settings  # ❌ Django dependency
from backend.settings.base import LOGGING  # ❌ Django dependency

# Workers import heavy Django modules
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.dev")
```

### Enterprise Plugin Structure
```
prompt-service/src/unstract/prompt_service/plugins_1/
├── summarize/           # Enterprise only
├── challenge/           # Enterprise only  
├── line-item-extraction/  # Enterprise only
├── table_extractor_v2/    # Enterprise only
└── simple_prompt_studio/  # Enterprise only
```

## Proposed Architecture: `unstract/prompt-service-workers`

### Package Structure
```
unstract/
├── prompt-service/          # Core logic package
└── prompt-service-workers/  # 🆕 Django-free worker package
    ├── README.md
    ├── pyproject.toml
    ├── src/
    │   └── unstract/
    │       └── prompt_service_workers/
    │           ├── __init__.py
    │           ├── app.py              # Celery app (Django-free)
    │           ├── config.py           # Environment-based config
    │           ├── helpers/            # 🎯 Helper classes for minimal imports
    │           │   ├── task_helper.py
    │           │   ├── plugin_helper.py
    │           │   └── enterprise_loader.py
    │           ├── workers/            # Actual worker tasks
    │           │   ├── extraction_worker.py
    │           │   ├── chunking_worker.py
    │           │   ├── autogen_worker.py
    │           │   └── evaluation_worker.py
    │           └── plugins/            # Plugin runtime
    │               ├── registry.py
    │               ├── loader.py
    │               └── enterprise/     # Enterprise plugins copied at build
    ├── docker/
    │   └── Dockerfile.workers
    └── tests/
```

## Key Design Principles

### 1. **Minimal Worker Imports**
Workers import only helpers, never heavy dependencies:

```python
# ✅ GOOD: Minimal worker pattern
from unstract.prompt_service_workers.helpers.task_helper import TaskHelper
from unstract.prompt_service_workers.helpers.plugin_helper import PluginHelper

@app.task
def extraction_worker(task_payload):
    helper = TaskHelper(task_payload)
    return helper.execute_extraction()
```

### 2. **Helper-Centric Architecture**
All complexity hidden in helper classes:

```python
# Worker stays minimal
@app.task  
def autogen_worker(task_payload):
    helper = TaskHelper(task_payload)
    return helper.execute_autogen_workflow()

# Helper handles all complexity
class TaskHelper:
    def execute_autogen_workflow(self):
        # Load enterprise plugins if available
        # Initialize SDK1 adapters
        # Execute complex logic
        # Return clean results
```

### 3. **Enterprise Plugin Integration**
Dynamic loading with cloud repo support:

```python
class EnterpriseLoader:
    def load_enterprise_plugins(self):
        """Load enterprise plugins from cloud repo at runtime"""
        if self.is_enterprise_environment():
            self.copy_cloud_plugins()
            self.register_enterprise_agents()
```

## Implementation Details

### Django-Free Celery Configuration

**File**: `unstract/prompt-service-workers/src/unstract/prompt_service_workers/app.py`
```python
from celery import Celery
from unstract.prompt_service_workers.config import WorkerConfig

# NO Django imports!
app = Celery('prompt-service-workers')

# Environment-based configuration (not Django settings)
app.config_from_object(WorkerConfig)

# Auto-discover tasks
app.autodiscover_tasks([
    'unstract.prompt_service_workers.workers'
])

# Register enterprise plugins at startup
from unstract.prompt_service_workers.helpers.enterprise_loader import EnterpriseLoader
EnterpriseLoader().initialize_at_startup()
```

**File**: `unstract/prompt-service-workers/src/unstract/prompt_service_workers/config.py`
```python
import os
from kombu import Queue

class WorkerConfig:
    """Django-free configuration using environment variables"""
    
    # Broker configuration
    broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    # Task serialization  
    accept_content = ['json']
    task_serializer = 'json'
    result_serializer = 'json'
    
    # Prompt service specific queues
    task_queues = [
        Queue('prompt_extraction', routing_key='prompt_extraction'),
        Queue('prompt_chunking', routing_key='prompt_chunking'),
        Queue('prompt_autogen', routing_key='prompt_autogen'),
        Queue('prompt_evaluation', routing_key='prompt_evaluation'),
    ]
    
    # Import paths for tasks
    imports = [
        'unstract.prompt_service_workers.workers.extraction_worker',
        'unstract.prompt_service_workers.workers.chunking_worker', 
        'unstract.prompt_service_workers.workers.autogen_worker',
        'unstract.prompt_service_workers.workers.evaluation_worker',
    ]
    
    # Worker settings
    task_acks_late = True
    worker_prefetch_multiplier = 1
    task_soft_time_limit = 1800  # 30 minutes
    task_time_limit = 2400       # 40 minutes
```

### Helper Classes for Minimal Imports

**File**: `unstract/prompt-service-workers/src/unstract/prompt_service_workers/helpers/task_helper.py`
```python
from typing import Any, Dict
from unstract.sdk1 import LLM, VectorDB, X2Text
from unstract.prompt_service_workers.helpers.plugin_helper import PluginHelper
from unstract.prompt_service_workers.config import WorkerConfig

class TaskHelper:
    """Main helper class that workers import. Handles all complexity."""
    
    def __init__(self, task_payload: Dict[str, Any]):
        self.payload = task_payload
        self.config = WorkerConfig()
        self.plugin_helper = PluginHelper()
        
    def execute_extraction(self) -> Dict[str, Any]:
        """Execute text extraction with minimal worker code"""
        try:
            # Initialize SDK1 adapters
            x2text = X2Text(
                adapter_instance_id=self.payload['extraction_settings']['x2text_instance_id']
            )
            
            # Perform extraction
            result = x2text.process(
                input_file_path=self.payload['file_path'],
                **self.payload['extraction_settings']
            )
            
            return {
                'status': 'success',
                'extracted_text': result.extracted_text,
                'metadata': result.extraction_metadata.__dict__
            }
            
        except Exception as e:
            return {
                'status': 'error', 
                'error': str(e)
            }
    
    def execute_autogen_workflow(self) -> Dict[str, Any]:
        """Execute Autogen workflow with enterprise agent support"""
        try:
            from unstract.autogen_client import ChatCompletionClient
            
            # Load enterprise agents if available
            agents = self.plugin_helper.get_available_agents(
                include_enterprise=True
            )
            
            # Create GraphFlow team
            team = self._create_autogen_team(agents)
            
            # Execute workflow
            results = team.execute()
            
            return {
                'status': 'success',
                'results': results,
                'agents_used': [agent.name for agent in agents]
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def execute_chunking_and_embedding(self) -> Dict[str, Any]:
        """Execute intelligent chunking with context-aware sizing"""
        try:
            # Get LLM context size for smart chunking
            llm = LLM(adapter_instance_id=self.payload['tool_settings']['llm'])
            context_size = llm.get_context_window_size()
            
            # Smart chunking logic
            from unstract.prompt_service.services.intelligent_chunking import IntelligentChunker
            chunker = IntelligentChunker(self.payload['tool_settings'])
            
            chunks = chunker.smart_chunk(
                text=self.payload['extracted_text'],
                context_size=context_size
            )
            
            # Generate embeddings
            embedding_adapter = self.payload['tool_settings']['embedding']
            embeddings = self._generate_embeddings(chunks, embedding_adapter)
            
            # Store in vector DB
            vector_db = VectorDB(adapter_instance_id=self.payload['tool_settings']['vector-db'])
            doc_id = vector_db.store_document(
                chunks=chunks,
                embeddings=embeddings,
                metadata=self.payload.get('metadata', {})
            )
            
            return {
                'status': 'success',
                'doc_id': doc_id,
                'chunk_count': len(chunks),
                'embedding_dimensions': len(embeddings[0]) if embeddings else 0
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
```

### Enterprise Plugin Integration

**File**: `unstract/prompt-service-workers/src/unstract/prompt_service_workers/helpers/plugin_helper.py`
```python
from typing import List, Dict, Any, Optional
import importlib
import os
from pathlib import Path

class PluginHelper:
    """Handles enterprise plugin loading and agent registration"""
    
    def __init__(self):
        self.enterprise_plugins = {}
        self.available_agents = {}
        self._load_plugins()
    
    def _load_plugins(self):
        """Load both core and enterprise plugins"""
        # Load core plugins (always available)
        self._load_core_plugins()
        
        # Load enterprise plugins (if environment supports)
        if self._is_enterprise_environment():
            self._load_enterprise_plugins()
    
    def _is_enterprise_environment(self) -> bool:
        """Check if running in enterprise environment"""
        return os.getenv('UNSTRACT_ENTERPRISE_MODE', 'false').lower() == 'true'
    
    def _load_core_plugins(self):
        """Load core plugins available in all deployments"""
        core_agents = {
            'generic_data_extraction_agent': {
                'class': 'GenericDataExtractionAgent',
                'tools': ['rag', 'calculator'],
                'enterprise': False
            },
            'data_collation_agent': {
                'class': 'DataCollationAgent', 
                'tools': ['string_concatenation', 'json_formatter'],
                'enterprise': False
            }
        }
        self.available_agents.update(core_agents)
    
    def _load_enterprise_plugins(self):
        """Load enterprise plugins from cloud repo"""
        try:
            # Enterprise plugins copied during Docker build from cloud repo
            enterprise_path = Path(__file__).parent.parent / 'plugins' / 'enterprise'
            
            if enterprise_path.exists():
                # Load summarize agent (enterprise)
                if (enterprise_path / 'summarize').exists():
                    self.available_agents['summarize_agent'] = {
                        'class': 'SummarizeAgent',
                        'tools': ['rag', 'summarization'],
                        'enterprise': True,
                        'module': 'unstract.prompt_service_workers.plugins.enterprise.summarize'
                    }
                
                # Load challenge agent (enterprise)
                if (enterprise_path / 'challenge').exists():
                    self.available_agents['challenger_agent'] = {
                        'class': 'ChallengerAgent',
                        'tools': ['rag', 'fact_checker', 'calculator'],
                        'enterprise': True,
                        'module': 'unstract.prompt_service_workers.plugins.enterprise.challenge'
                    }
                
                # Load table extraction agent (enterprise)
                if (enterprise_path / 'table_extractor_v2').exists():
                    self.available_agents['table_extraction_agent'] = {
                        'class': 'TableExtractionAgent',
                        'tools': ['calculator', 'omniparse', 'table_parser'],
                        'enterprise': True,
                        'module': 'unstract.prompt_service_workers.plugins.enterprise.table_extractor_v2'
                    }
                    
        except Exception as e:
            print(f"Warning: Failed to load enterprise plugins: {e}")
    
    def get_available_agents(self, include_enterprise: bool = True) -> List[Dict[str, Any]]:
        """Get list of available agents based on environment"""
        agents = []
        
        for agent_name, agent_config in self.available_agents.items():
            # Skip enterprise agents if not in enterprise mode
            if agent_config.get('enterprise', False) and not include_enterprise:
                continue
                
            # Skip enterprise agents if not in enterprise environment
            if agent_config.get('enterprise', False) and not self._is_enterprise_environment():
                continue
                
            agents.append({
                'name': agent_name,
                'config': agent_config
            })
        
        return agents
    
    def create_agent_instance(self, agent_name: str, agent_config: Dict[str, Any]) -> Any:
        """Dynamically create agent instance"""
        try:
            if agent_config.get('enterprise', False):
                # Load enterprise agent
                module_name = agent_config['module']
                module = importlib.import_module(module_name)
                agent_class = getattr(module, agent_config['class'])
            else:
                # Load core agent
                from unstract.prompt_service_workers.agents.core import (
                    GenericDataExtractionAgent, 
                    DataCollationAgent
                )
                agent_class = locals()[agent_config['class']]
            
            return agent_class(
                name=agent_name,
                tools=agent_config['tools']
            )
            
        except Exception as e:
            raise ImportError(f"Failed to create agent {agent_name}: {e}")
```

### Enterprise Plugin Loading Strategy

**File**: `unstract/prompt-service-workers/src/unstract/prompt_service_workers/helpers/enterprise_loader.py`
```python
import shutil
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class EnterpriseLoader:
    """Handles enterprise plugin loading from cloud repository"""
    
    def __init__(self):
        self.enterprise_path = Path(__file__).parent.parent / 'plugins' / 'enterprise'
        self.cloud_repo_path = os.getenv('CLOUD_PLUGINS_PATH', '/cloud-plugins')
    
    def initialize_at_startup(self):
        """Initialize enterprise plugins at worker startup"""
        if self._should_load_enterprise():
            logger.info("Loading enterprise plugins...")
            self.copy_cloud_plugins()
            self.validate_enterprise_plugins()
            logger.info("Enterprise plugins loaded successfully")
    
    def _should_load_enterprise(self) -> bool:
        """Check if enterprise plugins should be loaded"""
        return (
            os.getenv('UNSTRACT_ENTERPRISE_MODE', 'false').lower() == 'true' and
            os.path.exists(self.cloud_repo_path)
        )
    
    def copy_cloud_plugins(self):
        """Copy enterprise plugins from cloud repo to worker package"""
        try:
            # Ensure enterprise directory exists
            self.enterprise_path.mkdir(parents=True, exist_ok=True)
            
            # Copy enterprise plugins
            enterprise_plugins = [
                'summarize',
                'challenge', 
                'table_extractor_v2',
                'line-item-extraction'
            ]
            
            for plugin_name in enterprise_plugins:
                source_path = Path(self.cloud_repo_path) / plugin_name
                dest_path = self.enterprise_path / plugin_name
                
                if source_path.exists():
                    if dest_path.exists():
                        shutil.rmtree(dest_path)
                    shutil.copytree(source_path, dest_path)
                    logger.info(f"Copied enterprise plugin: {plugin_name}")
                else:
                    logger.warning(f"Enterprise plugin not found: {plugin_name}")
                    
        except Exception as e:
            logger.error(f"Failed to copy enterprise plugins: {e}")
            raise
    
    def validate_enterprise_plugins(self):
        """Validate that enterprise plugins are properly loaded"""
        required_files = [
            '__init__.py',
            'src/base.py'
        ]
        
        for plugin_dir in self.enterprise_path.iterdir():
            if plugin_dir.is_dir():
                for required_file in required_files:
                    file_path = plugin_dir / required_file
                    if not file_path.exists():
                        logger.warning(
                            f"Enterprise plugin {plugin_dir.name} missing {required_file}"
                        )
```

### Minimal Worker Implementation

**File**: `unstract/prompt-service-workers/src/unstract/prompt_service_workers/workers/autogen_worker.py`
```python
from unstract.prompt_service_workers.app import app
from unstract.prompt_service_workers.helpers.task_helper import TaskHelper

@app.task(bind=True, queue='prompt_autogen',
          max_retries=1, default_retry_delay=60,
          soft_time_limit=1800, time_limit=2400)
def agentic_data_extraction_task(self, task_payload):
    """
    Minimal worker - all complexity in TaskHelper
    Supports enterprise agents automatically
    """
    helper = TaskHelper(task_payload)
    return helper.execute_autogen_workflow()

@app.task(bind=True, queue='prompt_extraction', 
          max_retries=3, default_retry_delay=60)
def extract_text_task(self, task_payload):
    """Minimal extraction worker"""
    helper = TaskHelper(task_payload)
    return helper.execute_extraction()

@app.task(bind=True, queue='prompt_chunking',
          max_retries=2, default_retry_delay=30)
def chunking_and_embedding_task(self, task_payload):
    """Minimal chunking worker"""
    helper = TaskHelper(task_payload)
    return helper.execute_chunking_and_embedding()
```

### Docker Integration with Enterprise Support

**File**: `unstract/prompt-service-workers/docker/Dockerfile.workers`
```dockerfile
FROM python:3.12-slim

# Copy core packages
COPY unstract/prompt-service /app/unstract/prompt-service
COPY unstract/prompt-service-workers /app/unstract/prompt-service-workers
COPY unstract/core /app/unstract/core
COPY unstract/sdk1 /app/unstract/sdk1
COPY unstract/autogen-client /app/unstract/autogen-client

# Copy enterprise plugins if available (from cloud repo)
ARG ENTERPRISE_MODE=false
COPY cloud-plugins/ /cloud-plugins/
ENV UNSTRACT_ENTERPRISE_MODE=${ENTERPRISE_MODE}
ENV CLOUD_PLUGINS_PATH=/cloud-plugins

# Install dependencies
WORKDIR /app
RUN uv sync

# Entry point for workers
CMD ["celery", "-A", "unstract.prompt_service_workers.app", "worker", "-l", "info"]
```

### Integration with Backend

**File**: `backend/workflow_manager/workflow_v2/prompt_service_integration.py`
```python
from unstract.prompt_service_workers.workers.autogen_worker import agentic_data_extraction_task
from unstract.prompt_service_workers.workers.extraction_worker import extract_text_task

class PromptServiceIntegration:
    """Integration layer - backend calls workers, not Django-dependent services"""
    
    @staticmethod
    def execute_prompt_workflow(workflow_execution, file_hash):
        """Execute prompt workflow using Django-free workers"""
        
        task_payload = {
            'run_id': str(workflow_execution.id),
            'file_path': file_hash.file_path,
            'tool_settings': workflow_execution.get_tool_settings(),
            'outputs': workflow_execution.get_output_specifications()
        }
        
        # Chain workers
        result = extract_text_task.apply_async(args=[task_payload])
        # Continue with other workers...
        
        return result
```

## Benefits of This Approach

### ✅ **UN-2470 Compliance**
- Zero Django imports in workers
- Environment-based configuration
- Independent deployment capability

### ✅ **Minimal Worker Code**
- Workers are 3-5 lines each
- All complexity in reusable helpers
- Easy to test and maintain

### ✅ **Enterprise Plugin Support**
- Automatic detection of enterprise environment
- Dynamic loading from cloud repo
- Graceful fallback to core functionality

### ✅ **SDK1 Integration**
- Native SDK1 usage in helpers
- Consistent adapter management
- Performance optimized

### ✅ **Scalability**
- Independent worker scaling
- Queue-based load distribution
- Resource isolation

This architecture perfectly aligns with UN-2470 goals while providing a robust foundation for the prompt studio revamp with enterprise plugin support!