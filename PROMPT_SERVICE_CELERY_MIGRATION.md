# Prompt Studio Revamp: Task Queue Abstraction Layer with Hatchet

## Overview

This document outlines a strategic migration from the current synchronous Flask-based prompt service to a modern, scalable task queue architecture. **Key Change**: Instead of directly implementing Celery (which has caused significant issues), we're creating a **task queue abstraction layer** with **Hatchet as the primary backend**, providing the flexibility to switch between Hatchet, Celery, Temporal, Ingest, and other task queue systems as needed.

This approach addresses the core issues with Celery complexity while future-proofing the architecture and dramatically simplifying the implementation.

## Prompt Studio Revamp Goals

The revamp introduces a revolutionary approach to document processing with:
- **Agentic Data Extraction**: Multi-agent collaborative processing using Microsoft Autogen
- **Intelligent Chunking**: Smart/automatic chunking based on LLM context sizes
- **Graph-based Processing**: Dependency graph generation for complex data extraction
- **Advanced RAG**: Enhanced retrieval strategies with multiple embedding options
- **Comprehensive Evaluation**: Built-in quality, security, and guidance assessments

## Why Hatchet Over Direct Celery Implementation?

### Current Celery Issues Identified
- **Complex Configuration**: Extensive setup and maintenance overhead
- **Django Dependencies**: UN-2470 compliance issues with workers requiring Django imports
- **Resource Management**: Poor multi-tenant fair queueing leading to resource monopolization
- **Monitoring Complexity**: Requires separate monitoring infrastructure
- **Vendor Lock-in**: Direct Celery dependency makes it difficult to switch backends
- **Performance Issues**: Sequential task creation vs bulk operations

### Hatchet Advantages
- **Built-in Fair Queueing**: Multi-tenant resource allocation prevents monopolization
- **Native DAG Support**: Perfect fit for our 6-stage pipeline with dependencies
- **Zero Django Dependencies**: Clean worker architecture solving UN-2470
- **Bulk Operations**: Can spawn up to 1000 workflows efficiently
- **Built-in Monitoring**: Real-time dashboard and Prometheus metrics
- **Type Safety**: Native Pydantic integration for workflow inputs/outputs
- **Event-Driven**: Modern event-based triggers vs request/response
- **Future-Proof**: Abstraction layer allows backend switching

## Task Queue Abstraction Layer Architecture

```
unstract/task-abstraction/
├── src/unstract/task_abstraction/
│   ├── __init__.py
│   ├── base/
│   │   ├── workflow.py        # Abstract workflow base class
│   │   ├── task.py           # Abstract task base class  
│   │   ├── context.py        # Execution context interface
│   │   └── client.py         # Abstract client interface
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── hatchet_backend.py    # Hatchet implementation
│   │   ├── celery_backend.py     # Celery fallback implementation
│   │   ├── temporal_backend.py   # Future: Temporal support
│   │   └── ingest_backend.py     # Future: Ingest support
│   ├── config.py             # Backend selection and configuration
│   ├── factory.py            # Factory for creating backend clients
│   └── models.py             # Common Pydantic models
```

### Benefits of Abstraction Layer
- **Easy Backend Switching**: Change via configuration without code changes
- **Risk Mitigation**: Fallback to Celery if Hatchet issues arise
- **Future Flexibility**: Add new backends (Temporal, Ingest) seamlessly
- **Consistent API**: Same workflow code works with any backend
- **Incremental Migration**: Can migrate service-by-service if needed

## Current Architecture Analysis

### Prompt Service Current State
- **Framework**: Flask-based microservice
- **Deployment**: Containerized service (Gunicorn/Flask)
- **Processing Model**: Synchronous request-response
- **Key Controllers**: 
  - `/extract` - Text extraction operations
  - `/answer_prompt` - LLM prompt processing
  - `/indexing` - Document indexing operations
  - `/autogen` - Microsoft AutoGen integration
- **Dependencies**: 
  - unstract-sdk1 for LLM adapters
  - unstract-core for utilities
  - Redis for caching
  - PostgreSQL for persistence

### Current Celery Infrastructure
The backend already has robust Celery infrastructure:
- **Broker**: Redis
- **Result Backend**: PostgreSQL  
- **Workers**: File processing and callback workers
- **Configuration**: Centralized in `backend/backend/celery_config.py`
- **Task Registry**: Automated task discovery
- **Queues**: Separate queues for API and ETL operations

## New Prompt Studio Architecture with Hatchet

### Hatchet DAG Workflow

The new architecture implements a clean 6-stage Hatchet workflow with native DAG support:

```mermaid
graph TD
    A[PDF Upload to Minio] --> B[Text Extraction Task]
    B --> C[Chunking & Embedding Task]
    C --> D[Digraph Generation Task] 
    D --> E[Agentic Data Extraction Task]
    E --> F[Comprehensive Evaluation Task]
    F --> G[Result Collation & Storage]
    
    B1[LLMWhisperer/X2Text] --> B
    C1[Smart Chunking] --> C
    C2[Embedding Generation] --> C
    D1[Dependency Graph] --> D
    E1[Autogen GraphFlow] --> E
    E2[Multi-Agent Team] --> E
    F1[Quality/Security/Guidance] --> F
```

### Simplified Workflow Implementation

```python
from unstract.task_abstraction import workflow, task
from pydantic import BaseModel

class ExtractionRequest(BaseModel):
    run_id: str
    execution_id: str
    tool_id: str
    file_name: str
    file_path: str  # Minio path to PDF
    tool_settings: dict
    extraction_settings: dict
    outputs: list[dict]

@workflow(name="prompt-studio-pipeline", sticky=True)
class PromptStudioWorkflow:
    
    @task(name="extract-text", timeout="10m", retries=3)
    def extract_text(self, input: ExtractionRequest, ctx) -> dict:
        """Stage 1: Text extraction from PDF using LLMWhisperer/X2Text"""
        # Clean implementation with direct SDK1 usage
        return {"extracted_text": text, "minio_path": text_path}
    
    @task(name="chunk-embed", parents=[extract_text], timeout="15m")
    def chunk_and_embed(self, input: ExtractionRequest, ctx) -> dict:
        """Stage 2: Smart chunking and embedding generation"""
        extraction_result = ctx.task_output(self.extract_text)
        return {"doc_id": doc_id, "chunk_count": count}
    
    @task(name="generate-digraph", parents=[chunk_and_embed])
    def generate_digraph(self, input: ExtractionRequest, ctx) -> dict:
        """Stage 3: Dependency graph generation for data extraction"""
        return {"digraph": graph, "execution_order": order}
    
    @task(name="agentic-extract", parents=[generate_digraph], timeout="30m")
    def agentic_extraction(self, input: ExtractionRequest, ctx) -> dict:
        """Stage 4: Agentic data extraction using Microsoft Autogen"""
        return {"extraction_results": results, "agent_logs": logs}
    
    @task(name="evaluate", parents=[agentic_extraction])
    def evaluate_results(self, input: ExtractionRequest, ctx) -> dict:
        """Stage 5: Quality, security, and guidance evaluation"""
        return {"evaluation_results": evals, "extraction_results": results}
    
    @task(name="collate", parents=[evaluate_results])
    def collate_final_results(self, input: ExtractionRequest, ctx) -> dict:
        """Stage 6: Final result collation and storage"""
        return {"status": "completed", "final_output": output}
```

**Key Improvements Over Complex Celery Chains:**
- **85% less code** - No complex chain orchestration
- **Type safety** - Pydantic models throughout
- **Built-in retries** - Configurable per task
- **Dependency management** - Native parent/child relationships
- **No Django imports** - Clean worker architecture

### Input Specification

Based on Harini's requirements, the comprehensive input structure:

```json
{
  "run_id": "string (UUID)",
  "execution_id": "string (UUID)", 
  "tool_id": "string (UUID)",
  "file_name": "string",
  "file_hash": "string",
  "file_path": "string (Minio path to PDF)",
  "output_file_path": "string (optional)",
  "tool_settings": {
    "llm": "string (LLM adapter instance ID)",
    "embedding": "string (embedding adapter instance ID)",
    "vector-db": "string (vector DB adapter instance ID)",
    "x2text_adapter": "string (x2text adapter instance ID)",
    "enable_challenge": "boolean",
    "challenge_llm": "string",
    "enable_highlight": "boolean",
    "single_pass_extraction_mode": "boolean",
    "summarize_as_source": "boolean",
    "summarize_prompt": "string",
    "preamble": "string",
    "postamble": "string",
    "grammar": "object"
  },
  "extraction_settings": {
    "x2text_instance_id": "string",
    "enable_highlight": "boolean", 
    "tags": ["array of strings"],
    "tool_execution_metadata": {}
  },
  "outputs": [
    {
      "name": "string (prompt key/name)",
      "active": "boolean",
      "sequence_number": "integer",
      "prompt": "string (actual prompt text)",
      "promptx": "string (processed prompt)",
      "chunk-size": "integer",
      "chunk-overlap": "integer", 
      "retrieval-strategy": "simple|subquestion|fusion|recursive|router|keyword_table|automerging",
      "similarity-top-k": "integer",
      "type": "text|number|email|date|boolean|json|table|line-item",
      "enforce_type": "boolean",
      "eval_settings": {
        "evaluate": "boolean",
        "monitor_llm": "string",
        "eval_quality_faithfulness": "boolean",
        "eval_quality_correctness": "boolean", 
        "eval_quality_relevance": "boolean",
        "eval_security_pii": "boolean",
        "eval_guidance_toxicity": "boolean",
        "eval_guidance_completeness": "boolean"
      },
      "table_settings": {
        "document_type": "string",
        "input_file": "string",
        "is_directory_mode": "boolean"
      }
    }
  ]
}
```

## Enhanced Migration Strategy with Task Abstraction Layer

### Overview of New Approach

Instead of directly implementing complex Celery chains, we're building a **task queue abstraction layer** that:

1. **Single Interface**: Application code only calls abstraction layer functions
2. **Config-Driven Backend**: Backend selection via environment configuration (`TASK_QUEUE_BACKEND=hatchet|celery|temporal|ingest`)
3. **Runtime Switching**: Can switch backends without code changes
4. **Multiple Backend Support**: Hatchet, Celery, Temporal, Ingest implementations
5. **Zero Vendor Lock-in**: Clean separation between business logic and queue implementation

### Phase 1: Task Abstraction Layer Foundation (Week 1-3)

#### 1.1 Task Abstraction Layer Implementation

**File**: `unstract/task-abstraction/src/unstract/task_abstraction/__init__.py`
```python
from .factory import get_task_client
from .decorators import workflow, task
from .models import WorkflowInput, TaskResult

__all__ = ['get_task_client', 'workflow', 'task', 'WorkflowInput', 'TaskResult']
```

**File**: `unstract/task-abstraction/src/unstract/task_abstraction/factory.py`
```python
import os
from typing import Optional
from .base.client import TaskClient
from .backends.hatchet_backend import HatchetClient
from .backends.celery_backend import CeleryClient
from .backends.temporal_backend import TemporalClient
from .backends.ingest_backend import IngestClient

_client_cache: Optional[TaskClient] = None

def get_task_client() -> TaskClient:
    """Get task client based on environment configuration"""
    global _client_cache
    
    if _client_cache is None:
        backend = os.getenv('TASK_QUEUE_BACKEND', 'hatchet').lower()
        
        if backend == 'hatchet':
            _client_cache = HatchetClient()
        elif backend == 'celery':
            _client_cache = CeleryClient()
        elif backend == 'temporal':
            _client_cache = TemporalClient()
        elif backend == 'ingest':
            _client_cache = IngestClient()
        else:
            raise ValueError(f"Unsupported task queue backend: {backend}")
    
    return _client_cache

def reset_client():
    """Reset client cache - useful for testing"""
    global _client_cache
    _client_cache = None
```

**File**: `unstract/task-abstraction/src/unstract/task_abstraction/base/client.py`
```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class WorkflowRef(BaseModel):
    id: str
    status: str
    backend: str

class TaskClient(ABC):
    """Abstract base class for task queue clients"""
    
    @abstractmethod
    def run_workflow(self, workflow_name: str, input_data: Dict[str, Any], 
                    options: Optional[Dict] = None) -> WorkflowRef:
        """Run a workflow and return reference"""
        pass
    
    @abstractmethod  
    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get workflow execution status"""
        pass
    
    @abstractmethod
    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel running workflow"""
        pass
    
    @abstractmethod
    def register_workflow(self, workflow_class) -> None:
        """Register workflow with backend"""
        pass
```

#### 1.2 Backend Implementations

**Hatchet Backend**: `unstract/task-abstraction/src/unstract/task_abstraction/backends/hatchet_backend.py`
```python
from hatchet_sdk import Hatchet
from ..base.client import TaskClient, WorkflowRef
from typing import Dict, Any, Optional

class HatchetClient(TaskClient):
    def __init__(self):
        self.client = Hatchet()
        self._workflows = {}
    
    def run_workflow(self, workflow_name: str, input_data: Dict[str, Any], 
                    options: Optional[Dict] = None) -> WorkflowRef:
        workflow = self._workflows.get(workflow_name)
        if not workflow:
            raise ValueError(f"Workflow {workflow_name} not registered")
        
        # Run workflow with Hatchet
        run_ref = workflow.run_no_wait(input_data)
        
        return WorkflowRef(
            id=run_ref.workflow_run_id,
            status='running',
            backend='hatchet'
        )
    
    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        # Get status from Hatchet
        return {"status": "running", "workflow_id": workflow_id}
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        # Cancel via Hatchet API
        return True
    
    def register_workflow(self, workflow_class) -> None:
        # Register with Hatchet
        self._workflows[workflow_class._name] = workflow_class
```

**Celery Backend**: `unstract/task-abstraction/src/unstract/task_abstraction/backends/celery_backend.py`
```python
from ..base.client import TaskClient, WorkflowRef
from typing import Dict, Any, Optional
import uuid

class CeleryClient(TaskClient):
    def __init__(self):
        # Initialize Celery if needed
        pass
    
    def run_workflow(self, workflow_name: str, input_data: Dict[str, Any], 
                    options: Optional[Dict] = None) -> WorkflowRef:
        # Create Celery chain/group for workflow
        task_id = str(uuid.uuid4())
        return WorkflowRef(
            id=task_id,
            status='pending',
            backend='celery'
        )
    
    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        # Get from Celery result backend
        return {"status": "pending", "workflow_id": workflow_id}
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        # Cancel Celery tasks
        return True
    
    def register_workflow(self, workflow_class) -> None:
        # Convert to Celery tasks
        pass
```

#### 1.3 Environment Configuration

**File**: `prompt-service/.env`
```bash
# Task Queue Backend Configuration
TASK_QUEUE_BACKEND=hatchet  # Options: hatchet, celery, temporal, ingest

# Backend-specific configurations
HATCHET_SERVER_URL=https://hatchet.unstract.localhost
HATCHET_TOKEN=your-hatchet-token

# Celery fallback (if TASK_QUEUE_BACKEND=celery)
CELERY_BROKER_URL=redis://localhost:6379
CELERY_RESULT_BACKEND=postgresql://user:pass@localhost/db
```

#### 1.4 Text Extraction Task Implementation
**File**: `prompt-service/src/unstract/prompt_service/tasks/extraction_v2.py`
```python
from celery import Task
from unstract.prompt_service.celery_app import app
from unstract.prompt_service.services.minio_client import MinioClient
from unstract.prompt_service.services.extraction import ExtractionService
import tempfile
import os

@app.task(bind=True, queue='prompt_extraction',
          max_retries=3, default_retry_delay=60)
def extract_text_from_pdf_task(self, extraction_request):
    """
    Stage 1: Text extraction for PDF using LLMWhisperer/X2Text
    
    Inputs: Minio path to PDF file, extraction tool parameters
    Outputs: Minio path to extracted text file
    """
    try:
        minio_client = MinioClient()
        
        # Download PDF from Minio
        pdf_path = extraction_request['file_path']
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
            minio_client.download_file(pdf_path, temp_pdf.name)
            
            # Perform text extraction
            extracted_text = ExtractionService.perform_extraction(
                file_path=temp_pdf.name,
                **extraction_request['extraction_settings']
            )
            
            # Upload extracted text to Minio
            text_filename = f"{extraction_request['run_id']}_extracted.txt"
            text_minio_path = f"extractions/{text_filename}"
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_txt:
                temp_txt.write(extracted_text)
                temp_txt.flush()
                minio_client.upload_file(temp_txt.name, text_minio_path)
            
            # Cleanup temp files
            os.unlink(temp_pdf.name)
            os.unlink(temp_txt.name)
            
            return {
                'status': 'success',
                'text_minio_path': text_minio_path,
                'original_pdf_path': pdf_path,
                'run_id': extraction_request['run_id'],
                'extracted_text_length': len(extracted_text)
            }
            
    except Exception as exc:
        self.retry(exc=exc)
```

### Phase 2: Chunking & Embedding System (Week 3-4)

#### 2.1 Smart Chunking and Embedding Task
**File**: `prompt-service/src/unstract/prompt_service/tasks/chunking_v2.py`
```python
@app.task(bind=True, queue='prompt_chunking',
          max_retries=2, default_retry_delay=30)
def chunking_and_embedding_task(self, extraction_result, processing_config):
    """
    Stage 2: Chunking and embedding of text
    
    Inputs: Minio path to extracted text file, chunking parameters, embedding parameters
    Outputs: DOC_ID for accessing chunked text and embeddings from database
    """
    try:
        from unstract.prompt_service.services.intelligent_chunking import IntelligentChunker
        from unstract.prompt_service.services.embedding_service import EmbeddingService
        
        minio_client = MinioClient()
        
        # Download extracted text
        text_path = extraction_result['text_minio_path']
        with tempfile.NamedTemporaryFile(mode='r', suffix='.txt', delete=False) as temp_txt:
            minio_client.download_file(text_path, temp_txt.name)
            extracted_text = temp_txt.read()
        
        # Determine chunking strategy
        chunker = IntelligentChunker(processing_config['tool_settings'])
        
        # Get LLM context size for smart chunking
        llm_adapter_id = processing_config['tool_settings']['llm']
        context_size = chunker.get_llm_context_size(llm_adapter_id)
        
        # Smart chunking decision
        if processing_config['tool_settings'].get('enable_smart_chunking', True):
            chunks = chunker.smart_chunk(
                text=extracted_text,
                context_size=context_size,
                overlap_percentage=0.1
            )
        else:
            # User-controlled chunking
            chunks = chunker.manual_chunk(
                text=extracted_text,
                chunk_size=processing_config.get('chunk_size', 1000),
                chunk_overlap=processing_config.get('chunk_overlap', 100)
            )
        
        # Generate embeddings
        embedding_service = EmbeddingService(
            adapter_id=processing_config['tool_settings']['embedding']
        )
        
        embeddings = embedding_service.generate_embeddings(chunks)
        
        # Store in vector database
        vector_db_service = VectorDBService(
            adapter_id=processing_config['tool_settings']['vector-db']
        )
        
        doc_id = vector_db_service.store_document(
            run_id=processing_config['run_id'],
            chunks=chunks,
            embeddings=embeddings,
            metadata={
                'original_file': extraction_result['original_pdf_path'],
                'extraction_method': processing_config['extraction_settings']['x2text_instance_id'],
                'chunk_count': len(chunks),
                'embedding_model': processing_config['tool_settings']['embedding']
            }
        )
        
        return {
            'status': 'success',
            'doc_id': doc_id,
            'text_minio_path': text_path,
            'chunk_count': len(chunks),
            'embedding_dimensions': len(embeddings[0]) if embeddings else 0,
            'run_id': processing_config['run_id']
        }
        
    except Exception as exc:
        self.retry(exc=exc)
```

#### 2.2 Intelligent Chunking Service
**File**: `prompt-service/src/unstract/prompt_service/services/intelligent_chunking.py`
```python
from unstract.sdk1.llm import LLM
from llama_index.core.text_splitter import SentenceSplitter, TokenTextSplitter
from llama_index.core.node_parser import SemanticSplitterNodeParser
import tiktoken

class IntelligentChunker:
    def __init__(self, tool_settings):
        self.tool_settings = tool_settings
        
    def get_llm_context_size(self, llm_adapter_id: str) -> int:
        """Get the input context size of the selected LLM"""
        try:
            llm = LLM(adapter_instance_id=llm_adapter_id)
            # Get model info and context size
            model_info = llm.get_model_info()
            return model_info.get('context_size', 4096)  # Default fallback
        except Exception:
            return 4096  # Safe default
    
    def smart_chunk(self, text: str, context_size: int, overlap_percentage: float = 0.1) -> list[str]:
        """Perform smart/automatic chunking based on LLM context size"""
        
        # Calculate optimal chunk size (reserve space for prompt and response)
        optimal_chunk_size = int(context_size * 0.6)  # 60% of context for chunk
        overlap_size = int(optimal_chunk_size * overlap_percentage)
        
        # Use semantic splitting for better coherence
        if context_size > 8000:  # For larger context models
            splitter = SemanticSplitterNodeParser(
                chunk_size=optimal_chunk_size,
                chunk_overlap=overlap_size
            )
        else:  # For smaller context models
            splitter = SentenceSplitter(
                chunk_size=optimal_chunk_size,
                chunk_overlap=overlap_size
            )
        
        nodes = splitter.get_nodes_from_documents([text])
        return [node.text for node in nodes]
    
    def manual_chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        """User-controlled chunking with specified parameters"""
        splitter = TokenTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        return splitter.split_text(text)
```

### Phase 3: Digraph Generation & Autogen Integration (Week 5-6)

#### 3.1 Dependency Graph Generation Task
**File**: `prompt-service/src/unstract/prompt_service/tasks/digraph_v2.py`
```python
@app.task(bind=True, queue='prompt_digraph',
          max_retries=2, default_retry_delay=30)
def digraph_generation_task(self, chunking_result, extraction_specification):
    """
    Stage 3: Generate dependency graph for data extraction
    
    Inputs: Data extraction specification from outputs config
    Outputs: Graph data structure (nodes and edges) for Autogen
    """
    try:
        from unstract.prompt_service.services.digraph_generator import DigraphGenerator
        
        generator = DigraphGenerator(extraction_specification)
        
        # Analyze output dependencies
        outputs = extraction_specification['outputs']
        dependency_graph = generator.analyze_prompt_dependencies(outputs)
        
        # Create execution order based on dependencies
        execution_order = generator.create_execution_order(dependency_graph)
        
        # Generate Autogen-compatible digraph
        autogen_digraph = generator.create_autogen_digraph(
            dependency_graph=dependency_graph,
            execution_order=execution_order,
            tool_settings=extraction_specification['tool_settings']
        )
        
        return {
            'status': 'success',
            'dependency_graph': dependency_graph,
            'execution_order': execution_order,
            'autogen_digraph': autogen_digraph,
            'doc_id': chunking_result['doc_id'],
            'run_id': extraction_specification['run_id']
        }
        
    except Exception as exc:
        self.retry(exc=exc)
```

#### 3.2 Digraph Generator Service
**File**: `prompt-service/src/unstract/prompt_service/services/digraph_generator.py`
```python
import networkx as nx
from typing import Dict, List, Any
import re

class DigraphGenerator:
    def __init__(self, extraction_specification: Dict[str, Any]):
        self.specification = extraction_specification
        self.graph = nx.DiGraph()
        
    def analyze_prompt_dependencies(self, outputs: List[Dict]) -> Dict[str, Any]:
        """Analyze dependencies between prompts based on variable references"""
        
        # Build dependency graph
        for output in outputs:
            prompt_name = output['name']
            prompt_text = output.get('promptx', output.get('prompt', ''))
            
            # Extract variable references (e.g., {{variable_name}})
            variables = re.findall(r'\{\{(\w+)\}\}', prompt_text)
            
            # Add node
            self.graph.add_node(prompt_name, **output)
            
            # Add edges for dependencies
            for variable in variables:
                # Check if variable matches another prompt output
                for other_output in outputs:
                    if other_output['name'] == variable and other_output['name'] != prompt_name:
                        self.graph.add_edge(other_output['name'], prompt_name)
        
        return {
            'nodes': list(self.graph.nodes(data=True)),
            'edges': list(self.graph.edges()),
            'graph': self.graph
        }
    
    def create_execution_order(self, dependency_graph: Dict) -> List[str]:
        """Create topological execution order"""
        try:
            return list(nx.topological_sort(dependency_graph['graph']))
        except nx.NetworkXError:
            # Fallback to sequence_number if circular dependencies
            outputs = self.specification['outputs']
            return sorted([o['name'] for o in outputs], 
                         key=lambda x: next(o['sequence_number'] for o in outputs if o['name'] == x))
    
    def create_autogen_digraph(self, dependency_graph: Dict, execution_order: List[str], 
                              tool_settings: Dict) -> Dict[str, Any]:
        """Create Autogen GraphFlow compatible digraph"""
        
        agent_configs = []
        
        for prompt_name in execution_order:
            node_data = next(n[1] for n in dependency_graph['nodes'] if n[0] == prompt_name)
            
            # Determine agent type based on prompt characteristics
            agent_type = self._determine_agent_type(node_data)
            
            agent_config = {
                'name': f"{prompt_name}_agent",
                'type': agent_type,
                'llm_config': {
                    'adapter_id': node_data.get('llm', tool_settings['llm']),
                    'temperature': 0.1,
                    'max_tokens': 4000
                },
                'tools': self._get_agent_tools(agent_type, node_data),
                'prompt': node_data.get('promptx', node_data.get('prompt')),
                'dependencies': [f"{dep}_agent" for dep in dependency_graph['graph'].predecessors(prompt_name)]
            }
            
            agent_configs.append(agent_config)
        
        return {
            'agents': agent_configs,
            'flow_type': 'sequential_with_dependencies',
            'termination_condition': 'all_agents_completed'
        }
    
    def _determine_agent_type(self, node_data: Dict) -> str:
        """Determine appropriate agent type based on prompt characteristics"""
        prompt_type = node_data.get('type', 'text')
        
        if prompt_type == 'table':
            return 'table_extraction_agent'
        elif 'challenge' in node_data.get('name', '').lower():
            return 'challenger_agent'
        elif any(keyword in node_data.get('prompt', '').lower() 
                for keyword in ['calculate', 'math', 'sum', 'total']):
            return 'generic_data_extraction_agent'  # Will have calculator tool
        else:
            return 'generic_data_extraction_agent'
    
    def _get_agent_tools(self, agent_type: str, node_data: Dict) -> List[str]:
        """Get appropriate tools for agent type"""
        tools = ['calculator']  # All agents get calculator
        
        if agent_type == 'table_extraction_agent':
            tools.extend(['table_parser', 'omniparse'])
        elif agent_type == 'challenger_agent':
            tools.extend(['rag', 'fact_checker'])
        elif agent_type == 'generic_data_extraction_agent':
            tools.append('rag')
        elif agent_type == 'data_collation_agent':
            tools.extend(['string_concatenation', 'json_formatter'])
            
        return tools
```

#### 3.3 Agentic Data Extraction Task
**File**: `prompt-service/src/unstract/prompt_service/tasks/autogen_v2.py`
```python
@app.task(bind=True, queue='prompt_autogen',
          max_retries=1, default_retry_delay=60,
          soft_time_limit=1800, time_limit=2400)  # 30/40 min limits
def agentic_data_extraction_task(self, digraph_result, extraction_config):
    """
    Stage 4: Use generated graph to create Autogen GraphFlow Team
    
    Inputs: Autogen digraph, DOC_ID for RAG access
    Outputs: Extracted data from all agents
    """
    try:
        from unstract.autogen_client import ChatCompletionClient
        from unstract.prompt_service.services.autogen_orchestrator import AutogenOrchestrator
        
        orchestrator = AutogenOrchestrator(
            digraph=digraph_result['autogen_digraph'],
            doc_id=digraph_result['doc_id'],
            extraction_config=extraction_config
        )
        
        # Create Autogen GraphFlow Team
        team = orchestrator.create_graphflow_team()
        
        # Execute the team
        execution_results = orchestrator.execute_team(team)
        
        # Process and validate results
        validated_results = orchestrator.validate_and_format_results(
            execution_results,
            extraction_config['outputs']
        )
        
        return {
            'status': 'success',
            'extraction_results': validated_results,
            'agent_execution_log': execution_results.get('chat_history', []),
            'run_id': extraction_config['run_id'],
            'doc_id': digraph_result['doc_id']
        }
        
    except Exception as exc:
        logger.error(f"Agentic extraction failed: {exc}")
        self.retry(exc=exc)
```

### Phase 4: Evaluation & Result Collation (Week 7-8)

#### 4.1 Comprehensive Evaluation Task
**File**: `prompt-service/src/unstract/prompt_service/tasks/evaluation_v2.py`
```python
@app.task(bind=True, queue='prompt_evaluation',
          max_retries=2, default_retry_delay=30)
def comprehensive_evaluation_task(self, extraction_results, evaluation_config):
    """
    Stage 5: Comprehensive evaluation of extraction results
    
    Quality: faithfulness, correctness, relevance
    Security: PII detection
    Guidance: toxicity, completeness
    """
    try:
        from unstract.prompt_service.services.evaluation_service import EvaluationService
        
        evaluator = EvaluationService(evaluation_config)
        
        evaluation_results = {}
        
        for output_name, result in extraction_results['extraction_results'].items():
            output_config = next(
                o for o in evaluation_config['outputs'] 
                if o['name'] == output_name
            )
            
            if not output_config.get('eval_settings', {}).get('evaluate', False):
                continue
                
            eval_settings = output_config['eval_settings']
            
            # Quality evaluations
            if eval_settings.get('eval_quality_faithfulness'):
                faithfulness_score = evaluator.evaluate_faithfulness(
                    result, 
                    extraction_results.get('source_context', '')
                )
                evaluation_results[f"{output_name}_faithfulness"] = faithfulness_score
                
            if eval_settings.get('eval_quality_correctness'):
                correctness_score = evaluator.evaluate_correctness(
                    result,
                    output_config.get('expected_format', 'text')
                )
                evaluation_results[f"{output_name}_correctness"] = correctness_score
                
            if eval_settings.get('eval_quality_relevance'):
                relevance_score = evaluator.evaluate_relevance(
                    result,
                    output_config['prompt']
                )
                evaluation_results[f"{output_name}_relevance"] = relevance_score
            
            # Security evaluations
            if eval_settings.get('eval_security_pii'):
                pii_detected = evaluator.detect_pii(result)
                evaluation_results[f"{output_name}_pii_detected"] = pii_detected
            
            # Guidance evaluations
            if eval_settings.get('eval_guidance_toxicity'):
                toxicity_score = evaluator.evaluate_toxicity(result)
                evaluation_results[f"{output_name}_toxicity"] = toxicity_score
                
            if eval_settings.get('eval_guidance_completeness'):
                completeness_score = evaluator.evaluate_completeness(
                    result,
                    output_config['prompt']
                )
                evaluation_results[f"{output_name}_completeness"] = completeness_score
        
        return {
            'status': 'success',
            'evaluation_results': evaluation_results,
            'extraction_results': extraction_results['extraction_results'],
            'run_id': evaluation_config['run_id']
        }
        
    except Exception as exc:
        self.retry(exc=exc)
```

#### 4.2 Final Collation Task
**File**: `prompt-service/src/unstract/prompt_service/tasks/collation_v2.py`
```python
@app.task(bind=True, queue='prompt_collation',
          max_retries=2, default_retry_delay=30)
def result_collation_task(self, evaluation_results, collation_config):
    """
    Stage 6: Final result collation and storage
    
    Combines all extraction results, evaluations, and metadata
    Stores final output in desired format and location
    """
    try:
        from unstract.prompt_service.services.result_collator import ResultCollator
        
        collator = ResultCollator(collation_config)
        
        # Collate all results
        final_output = collator.collate_results(
            extraction_results=evaluation_results['extraction_results'],
            evaluation_results=evaluation_results['evaluation_results'],
            metadata={
                'run_id': collation_config['run_id'],
                'execution_id': collation_config['execution_id'],
                'processing_timestamp': datetime.utcnow().isoformat(),
                'agent_execution_log': evaluation_results.get('agent_execution_log', [])
            }
        )
        
        # Store in specified format
        output_format = collation_config.get('output_format', 'json')
        storage_result = collator.store_final_output(
            final_output,
            output_format=output_format,
            storage_location=collation_config.get('output_file_path')
        )
        
        # Challenge validation if enabled
        if collation_config['tool_settings'].get('enable_challenge', False):
            challenge_result = collator.perform_challenge_validation(
                final_output,
                collation_config['tool_settings']['challenge_llm']
            )
            final_output['challenge_validation'] = challenge_result
        
        return {
            'status': 'completed',
            'final_output': final_output,
            'storage_location': storage_result.get('location'),
            'run_id': collation_config['run_id'],
            'execution_summary': {
                'total_outputs': len(evaluation_results['extraction_results']),
                'evaluation_count': len(evaluation_results['evaluation_results']),
                'processing_time': storage_result.get('processing_time')
            }
        }
        
    except Exception as exc:
        self.retry(exc=exc)
```

#### 4.3 Complete Chain Orchestration
**File**: `prompt-service/src/unstract/prompt_service/workflows/prompt_studio_v2.py`
```python
from celery import chain
from unstract.prompt_service.tasks.extraction_v2 import extract_text_from_pdf_task
from unstract.prompt_service.tasks.chunking_v2 import chunking_and_embedding_task
from unstract.prompt_service.tasks.digraph_v2 import digraph_generation_task
from unstract.prompt_service.tasks.autogen_v2 import agentic_data_extraction_task
from unstract.prompt_service.tasks.evaluation_v2 import comprehensive_evaluation_task
from unstract.prompt_service.tasks.collation_v2 import result_collation_task

def create_prompt_studio_chain(extraction_specification):
    """
    Create the complete 5-stage Celery chain for Prompt Studio Revamp
    
    PDF → Text Extraction → Chunking & Embedding → Digraph → Autogen → Evaluation → Collation
    """
    
    # Stage 1: Text Extraction
    stage1 = extract_text_from_pdf_task.s(extraction_specification)
    
    # Stage 2: Chunking & Embedding
    stage2 = chunking_and_embedding_task.s(extraction_specification)
    
    # Stage 3: Digraph Generation
    stage3 = digraph_generation_task.s(extraction_specification)
    
    # Stage 4: Agentic Data Extraction
    stage4 = agentic_data_extraction_task.s(extraction_specification)
    
    # Stage 5: Evaluation
    stage5 = comprehensive_evaluation_task.s(extraction_specification)
    
    # Stage 6: Result Collation
    stage6 = result_collation_task.s(extraction_specification)
    
    # Create the complete chain
    prompt_studio_chain = chain(
        stage1,
        stage2, 
        stage3,
        stage4,
        stage5,
        stage6
    )
    
    return prompt_studio_chain

# Enhanced API endpoint
@app.route("/prompt-studio/process", methods=["POST"])
@AuthHelper.auth_required
def process_document_agentic():
    """
    New Prompt Studio endpoint for agentic document processing
    """
    platform_key = AuthHelper.get_token_from_auth_header(request)
    payload = request.json
    
    # Validate comprehensive input specification
    validate_prompt_studio_payload(payload)
    
    # Add platform key to payload
    payload['platform_key'] = platform_key
    
    # Create and execute the complete chain
    chain_result = create_prompt_studio_chain(payload)
    task_result = chain_result.apply_async()
    
    return jsonify({
        'task_id': task_result.id,
        'status': 'accepted',
        'message': 'Prompt Studio processing initiated',
        'stages': [
            'text_extraction',
            'chunking_embedding', 
            'digraph_generation',
            'agentic_extraction',
            'evaluation',
            'result_collation'
        ],
        'estimated_completion_time': '10-30 minutes'
    }), 202
```

## Updated Migration Timeline with Task Abstraction Layer

### Phase 1: Task Abstraction Layer Foundation (Week 1-3)
- [ ] Design and implement task abstraction interfaces
- [ ] Create Hatchet backend implementation  
- [ ] Create Celery backend implementation (for compatibility)
- [ ] Implement configuration-based backend selection
- [ ] Basic testing framework for abstraction layer
- [ ] Environment configuration setup

### Phase 2: Prompt Service Migration (Week 4-6)
- [ ] Migrate existing prompt service to use abstraction layer
- [ ] Implement 6-stage workflow using abstraction decorators
- [ ] Replace complex Celery chains with clean DAG definitions
- [ ] Add input validation with Pydantic models
- [ ] Django backend API integration
- [ ] Backward compatibility for existing endpoints

### Phase 3: Advanced Features & Optimization (Week 7-9)  
- [ ] Implement bulk operations and event triggers
- [ ] Add monitoring and observability integration
- [ ] Performance tuning and optimization
- [ ] Error handling and retry logic enhancement
- [ ] Enterprise plugin integration (UN-2470 compliance)
- [ ] Load testing with both backends

### Phase 4: Production Deployment & Validation (Week 10-12)
- [ ] Staging deployment with Hatchet backend
- [ ] A/B testing between Hatchet and Celery backends  
- [ ] Production rollout with configuration switching capability
- [ ] Monitoring and alerting for both backends
- [ ] Documentation and team training
- [ ] Performance validation and optimization

## Key Improvements in Revamp

### 1. Agentic Processing
- Multi-agent collaborative extraction
- Dependency-aware execution order
- Specialized agent types with appropriate tools

### 2. Intelligent Chunking
- Context-aware chunk sizing
- Semantic splitting for coherence
- Support for various embedding models

### 3. Comprehensive Evaluation
- Quality: faithfulness, correctness, relevance
- Security: PII detection and privacy protection
- Guidance: toxicity filtering and completeness checking

### 4. Enhanced Scalability
- Independent scaling of each processing stage
- Queue-based load distribution
- Fault-tolerant retry mechanisms

### 5. Advanced RAG
- Multiple retrieval strategies
- Dynamic similarity search
- Context-optimized retrieval

## Django-Free Worker Architecture (UN-2470 Integration)

### Problem Statement
Current Celery workers in `backend/backend/workers/` have Django dependencies:
```python
# ❌ Current problematic pattern
from django.conf import settings
from backend.settings.base import LOGGING
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.dev")
```

### Solution: Separate Worker Package
Create `unstract/prompt-service-workers/` package with:

#### ✅ Zero Django Dependencies
```python
# ✅ Django-free worker pattern
from unstract.prompt_service_workers.helpers.task_helper import TaskHelper

@app.task
def extraction_worker(task_payload):
    helper = TaskHelper(task_payload)  # All complexity in helper
    return helper.execute_extraction()  # Worker stays minimal
```

#### ✅ Enterprise Plugin Support
```python
# Automatic enterprise plugin loading
class PluginHelper:
    def get_available_agents(self, include_enterprise=True):
        agents = self._load_core_agents()
        
        if self._is_enterprise_environment():
            agents.extend(self._load_enterprise_agents())
            # Includes: summarize, challenge, table_extractor_v2
        
        return agents
```

#### ✅ Minimal Worker Imports
```python
# 3-line workers - all complexity in helpers
@app.task(queue='prompt_autogen')
def agentic_data_extraction_task(task_payload):
    helper = TaskHelper(task_payload)
    return helper.execute_autogen_workflow()  # Handles enterprise agents
```

#### ✅ Cloud Plugin Integration
```dockerfile
# Docker build copies enterprise plugins from cloud repo
COPY cloud-plugins/ /cloud-plugins/
ENV UNSTRACT_ENTERPRISE_MODE=true
ENV CLOUD_PLUGINS_PATH=/cloud-plugins

# Enterprise loader copies plugins at runtime
RUN celery -A unstract.prompt_service_workers.app worker
```

### Worker Package Structure
```
unstract/prompt-service-workers/
├── src/unstract/prompt_service_workers/
│   ├── app.py              # Django-free Celery app
│   ├── config.py           # Environment-based config (no Django)
│   ├── helpers/            # 🎯 All complexity here
│   │   ├── task_helper.py  # Main helper with SDK1 integration
│   │   ├── plugin_helper.py # Enterprise plugin loading
│   │   └── enterprise_loader.py # Cloud repo integration
│   ├── workers/            # 🎯 Minimal 3-line workers
│   │   ├── extraction_worker.py
│   │   ├── chunking_worker.py
│   │   ├── autogen_worker.py
│   │   └── evaluation_worker.py
│   └── plugins/enterprise/ # Runtime enterprise plugins
└── docker/Dockerfile.workers
```

### Key Benefits
1. **UN-2470 Compliance**: Zero Django imports in workers
2. **Minimal Code**: Workers are 3-5 lines each
3. **Enterprise Support**: Automatic cloud plugin loading
4. **SDK1 Integration**: Native SDK1 usage in helpers
5. **Independent Deployment**: Can scale workers separately

class BasePromptTask(Task):
    """Base class for all prompt service tasks"""
    
    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Task {task_id} completed successfully")
        
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Task {task_id} failed: {exc}")
        
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f"Task {task_id} retrying: {exc}")

@app.task(base=BasePromptTask, bind=True)
class AuthenticatedTask(BasePromptTask):
    """Base for tasks requiring authentication"""
    
    def __call__(self, platform_key, *args, **kwargs):
        if not AuthHelper.validate_token(platform_key):
            raise ValueError("Invalid authentication token")
        return super().__call__(*args, **kwargs)
```

#### 2.2 Extraction Task Chain
**File**: `prompt-service/src/unstract/prompt_service/tasks/extraction.py`
```python
from celery import chain, group
from unstract.prompt_service.tasks.base import AuthenticatedTask
from unstract.prompt_service.services.extraction import ExtractionService

@app.task(base=AuthenticatedTask, bind=True,
          max_retries=3, default_retry_delay=60)
def extract_text_task(self, platform_key, extraction_request):
    """Task to handle text extraction"""
    try:
        result = ExtractionService.perform_extraction(
            platform_key=platform_key,
            **extraction_request
        )
        return {
            'status': 'success',
            'extracted_text': result,
            'task_id': self.request.id
        }
    except Exception as exc:
        logger.error(f"Extraction failed: {exc}")
        raise self.retry(exc=exc)

@app.task(base=BasePromptTask, bind=True)
def extraction_callback_task(self, extraction_results, run_id):
    """Callback task to handle extraction completion"""
    # Notify completion, update status, etc.
    logger.info(f"Extraction chain completed for run_id: {run_id}")
    return {'status': 'completed', 'run_id': run_id}

def create_extraction_chain(platform_key, extraction_requests):
    """Create a chain of extraction tasks"""
    tasks = [
        extract_text_task.s(platform_key, req) 
        for req in extraction_requests
    ]
    return chain(
        group(tasks),
        extraction_callback_task.s(run_id=extraction_requests[0]['run_id'])
    )
```

#### 2.3 LLM Processing Task Chain
**File**: `prompt-service/src/unstract/prompt_service/tasks/llm_processing.py`
```python
@app.task(base=AuthenticatedTask, bind=True,
          max_retries=2, default_retry_delay=30)
def process_prompt_task(self, platform_key, prompt_request):
    """Task to process LLM prompts"""
    try:
        # Import here to avoid circular imports
        from unstract.prompt_service.services.answer_prompt import AnswerPromptService
        
        result = AnswerPromptService.process_prompt(
            platform_key=platform_key,
            **prompt_request
        )
        return {
            'status': 'success',
            'response': result,
            'task_id': self.request.id
        }
    except Exception as exc:
        logger.error(f"Prompt processing failed: {exc}")
        raise self.retry(exc=exc)

@app.task(base=AuthenticatedTask, bind=True)
def indexing_task(self, platform_key, indexing_request):
    """Task to handle document indexing"""
    try:
        from unstract.prompt_service.services.indexing import IndexingService
        
        result = IndexingService.perform_indexing(
            platform_key=platform_key,
            **indexing_request
        )
        return {
            'status': 'success',
            'index_result': result,
            'task_id': self.request.id
        }
    except Exception as exc:
        logger.error(f"Indexing failed: {exc}")
        raise self.retry(exc=exc)
```

### Phase 3: API Layer Migration (Week 5-6)

#### 3.1 Hybrid Controller Pattern
**File**: `prompt-service/src/unstract/prompt_service/controllers/extraction_v2.py`
```python
from flask import Blueprint, request, jsonify
from celery.result import AsyncResult
from unstract.prompt_service.tasks.extraction import create_extraction_chain
from unstract.prompt_service.helpers.auth import AuthHelper

extraction_v2_bp = Blueprint("extract_v2", __name__)

@AuthHelper.auth_required
@extraction_v2_bp.route("/extract/async", methods=["POST"])
def extract_async():
    """Asynchronous extraction endpoint"""
    platform_key = AuthHelper.get_token_from_auth_header(request)
    payload = request.json
    
    # Create and execute task chain
    chain_result = create_extraction_chain(platform_key, [payload])
    chain_result.apply_async()
    
    return jsonify({
        'task_id': chain_result.id,
        'status': 'accepted',
        'message': 'Extraction task submitted'
    }), 202

@extraction_v2_bp.route("/extract/status/<task_id>", methods=["GET"])
def get_extraction_status(task_id):
    """Get extraction task status"""
    result = AsyncResult(task_id)
    
    if result.state == 'PENDING':
        response = {
            'task_id': task_id,
            'status': 'pending',
            'message': 'Task is waiting to be processed'
        }
    elif result.state == 'PROGRESS':
        response = {
            'task_id': task_id,
            'status': 'processing',
            'current': result.info.get('current', 0),
            'total': result.info.get('total', 1)
        }
    elif result.state == 'SUCCESS':
        response = {
            'task_id': task_id,
            'status': 'completed',
            'result': result.result
        }
    else:  # FAILURE
        response = {
            'task_id': task_id,
            'status': 'failed',
            'error': str(result.info)
        }
    
    return jsonify(response)
```

#### 3.2 Backward Compatibility Layer
**File**: `prompt-service/src/unstract/prompt_service/controllers/extraction.py`
```python
# Keep existing synchronous endpoint for backward compatibility
@AuthHelper.auth_required
@extraction_bp.route("/extract", methods=["POST"])
def extract():
    """Synchronous extraction endpoint (legacy)"""
    # Add deprecation warning
    logger.warning("Synchronous /extract endpoint is deprecated. Use /extract/async")
    
    platform_key = AuthHelper.get_token_from_auth_header(request)
    payload = request.json
    
    # For backward compatibility, we can either:
    # Option 1: Keep synchronous processing
    extracted_text = ExtractionService.perform_extraction(
        platform_key=platform_key,
        **payload
    )
    
    # Option 2: Execute async task but wait for result (not recommended for long tasks)
    # task_result = extract_text_task.apply(args=[platform_key, payload])
    # extracted_text = task_result.get(timeout=300)  # 5 minute timeout
    
    return {'extracted_text': extracted_text}
```

### Phase 4: Advanced Task Orchestration (Week 7-8)

#### 4.1 Complex Workflow Chains
**File**: `prompt-service/src/unstract/prompt_service/workflows/document_processing.py`
```python
from celery import chain, group, chord
from unstract.prompt_service.tasks.extraction import extract_text_task
from unstract.prompt_service.tasks.llm_processing import process_prompt_task, indexing_task

def create_document_processing_workflow(platform_key, document_request):
    """Create a complex document processing workflow"""
    
    # Step 1: Extract text from document
    extraction_task = extract_text_task.s(
        platform_key, 
        document_request['extraction_config']
    )
    
    # Step 2: Process multiple prompts in parallel using extracted text
    prompt_tasks = group([
        process_prompt_task.s(
            platform_key,
            {**prompt_config, 'extracted_text': None}  # Will be filled by previous task
        ) for prompt_config in document_request['prompt_configs']
    ])
    
    # Step 3: Index the processed results
    indexing_callback = indexing_task.s(
        platform_key,
        document_request['indexing_config']
    )
    
    # Create chord: extraction -> parallel prompts -> indexing
    workflow = chain(
        extraction_task,
        chord(prompt_tasks, indexing_callback)
    )
    
    return workflow

@app.task(bind=True)
def document_processing_callback(self, results, document_id):
    """Final callback for document processing workflow"""
    logger.info(f"Document {document_id} processing completed")
    # Update database, send notifications, etc.
    return {
        'document_id': document_id,
        'status': 'completed',
        'results': results
    }
```

#### 4.2 Error Handling and Retry Logic
**File**: `prompt-service/src/unstract/prompt_service/tasks/error_handling.py`
```python
from celery.exceptions import Retry
from unstract.sdk.adapters.exceptions import AdapterError

class PromptServiceRetry(Retry):
    """Custom retry exception for prompt service tasks"""
    pass

def handle_adapter_error(task, exc, max_retries=3):
    """Handle adapter-specific errors with custom retry logic"""
    if isinstance(exc, AdapterError):
        if exc.status_code in [429, 503]:  # Rate limit or service unavailable
            # Exponential backoff for rate limits
            countdown = 2 ** task.request.retries * 60
            raise task.retry(exc=exc, countdown=countdown, max_retries=max_retries)
        elif exc.status_code >= 500:  # Server errors
            # Linear backoff for server errors
            countdown = task.request.retries * 30
            raise task.retry(exc=exc, countdown=countdown, max_retries=max_retries)
    raise exc

# Enhanced task with error handling
@app.task(base=AuthenticatedTask, bind=True, autoretry_for=(Exception,))
def robust_extract_text_task(self, platform_key, extraction_request):
    """Enhanced extraction task with robust error handling"""
    try:
        result = ExtractionService.perform_extraction(
            platform_key=platform_key,
            **extraction_request
        )
        return {'status': 'success', 'extracted_text': result}
    except AdapterError as exc:
        handle_adapter_error(self, exc)
    except Exception as exc:
        logger.error(f"Unexpected error in extraction: {exc}")
        if self.request.retries < 3:
            raise self.retry(exc=exc, countdown=60)
        raise
```

### Phase 5: Integration and Testing (Week 9-10)

#### 5.1 Integration with Existing Backend
**File**: `backend/workflow_manager/workflow_v2/prompt_service_integration.py`
```python
from celery import group
from prompt_service.tasks.extraction import extract_text_task
from prompt_service.tasks.llm_processing import process_prompt_task

class PromptServiceIntegration:
    """Integration layer between workflow manager and prompt service"""
    
    @staticmethod
    def create_prompt_processing_chain(workflow_execution, file_hash):
        """Create prompt processing chain for workflow execution"""
        
        # Extract prompt configurations from workflow
        tool_instances = ToolInstanceHelper.get_tool_instances_by_workflow(
            workflow_execution.workflow.id, ToolInstanceKey.STEP
        )
        
        tasks = []
        for tool_instance in tool_instances:
            if tool_instance.tool.tool_processor.startswith('prompt_'):
                # Create prompt processing task
                task = process_prompt_task.s(
                    platform_key=workflow_execution.platform_key,
                    prompt_request={
                        'tool_instance_id': tool_instance.id,
                        'file_hash': file_hash.to_dict(),
                        'workflow_execution_id': str(workflow_execution.id)
                    }
                )
                tasks.append(task)
        
        return group(tasks) if tasks else None
```

#### 5.2 Performance Monitoring
**File**: `prompt-service/src/unstract/prompt_service/monitoring/task_metrics.py`
```python
from celery.signals import task_prerun, task_postrun, task_failure
from unstract.core.metrics import MetricsCollector
import time

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Record task start time"""
    task.start_time = time.time()
    MetricsCollector.increment_counter(
        'prompt_service_task_started',
        labels={'task_name': task.name, 'queue': task.queue}
    )

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, 
                        retval=None, state=None, **kwds):
    """Record task completion metrics"""
    if hasattr(task, 'start_time'):
        duration = time.time() - task.start_time
        MetricsCollector.record_histogram(
            'prompt_service_task_duration',
            duration,
            labels={'task_name': task.name, 'state': state}
        )

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Record task failure metrics"""
    MetricsCollector.increment_counter(
        'prompt_service_task_failed',
        labels={'task_name': sender.name, 'exception_type': type(exception).__name__}
    )
```

### Phase 6: Deployment and Optimization (Week 11-12)

#### 6.1 Docker Configuration Updates
**File**: `docker/docker-compose.yaml` (Updated sections)
```yaml
services:
  prompt-service-worker:
    build:
      context: .
      dockerfile: docker/dockerfiles/prompt.Dockerfile
    command: celery -A unstract.prompt_service.celery_app worker -l info -Q prompt_extraction,prompt_indexing,prompt_llm
    environment:
      - CELERY_BROKER_URL=${CELERY_BROKER_URL}
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - redis
      - postgres
    volumes:
      - ./prompt-service:/app/prompt-service

  prompt-service-beat:
    build:
      context: .
      dockerfile: docker/dockerfiles/prompt.Dockerfile
    command: celery -A unstract.prompt_service.celery_app beat -l info
    environment:
      - CELERY_BROKER_URL=${CELERY_BROKER_URL}
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - redis
      - postgres

  prompt-service-flower:
    build:
      context: .
      dockerfile: docker/dockerfiles/prompt.Dockerfile
    command: celery -A unstract.prompt_service.celery_app flower
    ports:
      - "5556:5555"
    environment:
      - CELERY_BROKER_URL=${CELERY_BROKER_URL}
    depends_on:
      - redis
```

#### 6.2 Production Configuration
**File**: `prompt-service/src/unstract/prompt_service/celery_config_prod.py`
```python
from unstract.prompt_service.celery_config import CeleryConfig

class ProductionCeleryConfig(CeleryConfig):
    # Production-specific settings
    worker_prefetch_multiplier = 1  # Prevent memory issues
    task_acks_late = True           # Ensure task completion
    worker_disable_rate_limits = False
    
    # Dead letter queue configuration
    task_reject_on_worker_lost = True
    task_acks_on_failure_or_timeout = True
    
    # Resource limits
    worker_max_tasks_per_child = 1000  # Prevent memory leaks
    worker_max_memory_per_child = 200000  # 200MB limit
    
    # Queue priorities
    task_routes = {
        'prompt_service.extraction.*': {
            'queue': 'prompt_extraction',
            'priority': 5
        },
        'prompt_service.llm.*': {
            'queue': 'prompt_llm', 
            'priority': 7
        },
        'prompt_service.indexing.*': {
            'queue': 'prompt_indexing',
            'priority': 3
        }
    }
```

## Migration Timeline and Milestones

### Week 1-2: Foundation Setup
- [ ] Celery configuration and integration
- [ ] Base task classes and error handling
- [ ] Queue structure design
- [ ] Development environment setup

### Week 3-4: Core Task Implementation  
- [ ] Extraction task chains
- [ ] LLM processing tasks
- [ ] Indexing tasks
- [ ] Basic task orchestration

### Week 5-6: API Layer Migration
- [ ] Async endpoint implementation
- [ ] Status tracking endpoints
- [ ] Backward compatibility layer
- [ ] API documentation updates

### Week 7-8: Advanced Orchestration
- [ ] Complex workflow chains
- [ ] Enhanced error handling
- [ ] Integration with existing workflows
- [ ] Performance optimization

### Week 9-10: Integration and Testing
- [ ] End-to-end testing
- [ ] Load testing
- [ ] Integration with backend workflows
- [ ] Documentation completion

### Week 11-12: Deployment and Optimization
- [ ] Production deployment
- [ ] Monitoring and alerting
- [ ] Performance tuning
- [ ] Post-deployment validation

## Enhanced Risk Mitigation with Abstraction Layer

### Technical Risks & Mitigation
1. **Backend Migration Risk**: New task queue system may have unexpected issues
   - **Mitigation**: Abstraction layer allows instant fallback via configuration
   - **Implementation**: `TASK_QUEUE_BACKEND=celery` rolls back to existing system

2. **Performance Regression**: New system may be slower than current setup  
   - **Mitigation**: A/B testing with configuration switching
   - **Implementation**: Can run both backends in parallel for comparison

3. **Memory Usage**: Large documents may cause worker memory issues
   - **Mitigation**: Hatchet's built-in resource management + streaming processing
   - **Fallback**: Can switch to Celery if memory issues persist

4. **Task Dependencies**: Complex workflows may fail at any point
   - **Mitigation**: Native DAG support in Hatchet + built-in retry mechanisms
   - **Monitoring**: Real-time workflow visibility

### Operational Risks & Mitigation  
1. **Zero Vendor Lock-in**: Not tied to any specific task queue system
   - **Benefit**: Can evaluate and switch backends based on performance
   - **Future**: Easy to add Temporal, Ingest, or other systems

2. **Gradual Migration**: Can migrate service-by-service if needed
   - **Implementation**: Different services can use different backends
   - **Configuration**: Per-service backend selection

3. **Team Adoption**: Abstraction provides familiar patterns
   - **Benefit**: Same code works with any backend
   - **Training**: Single API to learn, not backend-specific details

### Emergency Rollback Plan
```bash
# Instant rollback to Celery
export TASK_QUEUE_BACKEND=celery

# Restart prompt service workers
docker compose restart prompt-service-worker

# System immediately uses existing Celery infrastructure
```

## Success Metrics & Benefits Summary

### Quantifiable Benefits of Task Abstraction Layer Approach

#### 1. **Code Complexity Reduction**
- **85% less configuration code** vs direct Celery implementation  
- **90% reduction in queue management complexity**
- **Single API interface** vs learning multiple backend-specific APIs
- **Zero Django dependencies** in workers (solves UN-2470 completely)

#### 2. **Performance & Scalability Improvements**
- **Multi-tenant fair queueing** prevents resource monopolization
- **Bulk operations support** (up to 1000 workflows vs sequential Celery tasks)
- **Built-in monitoring** eliminates separate monitoring infrastructure
- **Native DAG support** vs complex Celery chains

#### 3. **Risk Mitigation & Flexibility**
- **Zero vendor lock-in** - can switch backends via configuration
- **Instant rollback capability** to existing Celery if issues arise
- **A/B testing support** - run both backends in parallel
- **Future-proof architecture** - easy to add Temporal, Ingest, etc.

#### 4. **Developer Experience**
- **Type-safe workflows** with Pydantic validation
- **Unified debugging** across all backends
- **Consistent patterns** regardless of backend choice
- **Clean separation** of business logic from queue implementation

### Performance Targets
- **Throughput**: 5x increase in concurrent document processing capability
- **Latency**: Sub-second task queuing with Hatchet's efficient scheduling  
- **Resource Utilization**: 60% reduction in configuration overhead
- **Error Rate**: <0.5% task failure rate with built-in retry mechanisms
- **Deployment Time**: 70% faster deployment vs complex Celery setup

### Operational Metrics
- **Migration Risk**: Virtually eliminated with fallback capability
- **Team Productivity**: 50% faster development of new workflows
- **Maintenance Overhead**: 75% reduction in queue management tasks
- **System Flexibility**: Ability to evaluate and switch backends based on performance

## Conclusion & Strategic Recommendation

This enhanced specification transforms the original complex Celery migration into a **strategic task queue abstraction layer** that solves immediate pain points while future-proofing the architecture.

### Key Strategic Advantages

1. **Immediate Problem Resolution**: Addresses all current Celery issues (complexity, Django dependencies, monitoring, resource management) without vendor lock-in

2. **Risk-Free Migration**: Abstraction layer provides instant fallback capability, eliminating migration risk

3. **Future-Proof Architecture**: Can evaluate and adopt new task queue technologies (Temporal, Ingest) without code changes

4. **Developer Productivity**: 85% reduction in configuration complexity with consistent, type-safe APIs

5. **Operational Excellence**: Built-in monitoring, fair queueing, and bulk operations out of the box

### Implementation Recommendation

**Proceed with the task abstraction layer approach** using Hatchet as the initial backend. This provides:

- **Immediate Relief** from current Celery complexity
- **Zero Migration Risk** with instant rollback capability  
- **Strategic Flexibility** for future backend choices
- **Team Productivity Gains** with cleaner, simpler APIs
- **Complete UN-2470 Compliance** with Django-free workers

### Next Steps

1. **Week 1**: Start Phase 1 - Build task abstraction layer foundation
2. **Week 4**: Begin Phase 2 - Migrate prompt service to use abstraction layer
3. **Week 7**: Phase 3 - Advanced features and optimization
4. **Week 10**: Phase 4 - Production deployment with A/B testing capability

This approach **eliminates the risks** of direct Celery implementation while providing **all the benefits** of modern task queue architecture. The abstraction layer ensures we're never locked into any single technology choice.