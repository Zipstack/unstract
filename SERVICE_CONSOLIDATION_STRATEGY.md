# Service Consolidation Strategy: Eliminating Prompt Studio

## 🎯 **Overview**

This document outlines the strategy for eliminating the Flask Prompt Studio service by converting its functionality into decoupled helper functions that workflows call directly. This architectural transformation simplifies the platform while maintaining all functionality.

## 🏗️ **Architecture Transformation**

### **BEFORE: Tightly Coupled Services**
```
┌─────────────────┐    HTTP     ┌─────────────────┐    Tasks    ┌─────────────────┐
│                 │   Requests  │                 │    Queue    │                 │
│   Django        │◄────────────┤  Flask Prompt   │◄────────────┤     Celery      │
│   Backend       │             │    Service      │             │    Workers      │
│                 │             │  (Tightly       │             │                 │
└─────────────────┘             │   Coupled)      │             └─────────────────┘
         │                      └─────────────────┘                      │
         │                               │                               │
         ▼                               ▼                               ▼
┌─────────────────┐             ┌─────────────────┐             ┌─────────────────┐
│   PostgreSQL    │             │  LLM Adapters   │             │  Document Proc. │
│   Database      │             │   (OpenAI,      │             │   X2Text, etc.  │
│                 │             │   Anthropic)    │             │                 │
└─────────────────┘             └─────────────────┘             └─────────────────┘
```

### **AFTER: Workflow-Driven Architecture**
```
┌─────────────────┐   Workflow  ┌─────────────────┐   Backend   ┌─────────────────┐
│                 │   Triggers  │                 │   Select.   │                 │
│   Django        │────────────►│  Task Queue     │────────────►│    Hatchet      │
│   Backend       │             │  Abstraction    │             │   (Primary)     │
│                 │             │   Layer         │             │                 │
└─────────────────┘             └─────────────────┘             └─────────────────┘
         │                               │                               │
         │                    Alternative Backend                       │
         │                               │                               │
         ▼                               ▼                               ▼
┌─────────────────┐             ┌─────────────────┐             ┌─────────────────┐
│   PostgreSQL    │             │     Celery      │             │   Workflow      │
│   Database      │             │   (Migration)   │             │   Execution     │
│   (Config Only) │             │                 │             │                 │
└─────────────────┘             └─────────────────┘             └─────────────────┘
                                                                         │
                                                                         │
                                                                         ▼
                                ┌─────────────────┐             ┌─────────────────┐
                                │   Prompt        │             │   Document      │
                                │   Helpers       │             │   Processing    │
                                │   (Library)     │◄────────────┤   Workflows     │
                                └─────────────────┘             └─────────────────┘
                                         │                               │
                                         ▼                               ▼
                                ┌─────────────────┐             ┌─────────────────┐
                                │  LLM Adapters   │             │   X2Text, etc.  │
                                │   (OpenAI,      │             │   (Tools)       │
                                │   Anthropic)    │             │                 │
                                └─────────────────┘             └─────────────────┘
```

## 📦 **Component Transformation**

### **1. Prompt Studio Service → Helper Library**

**BEFORE:**
```python
# Flask service endpoint
@app.route("/api/process-prompt", methods=["POST"])
def process_prompt():
    # Complex Flask logic with Django coupling
    return jsonify(result)
```

**AFTER:**
```python
# Helper function in workflow
from unstract.prompt_helpers import LLMHelper

def process_llm_task(self, input_data, ctx):
    llm_helper = LLMHelper(adapter_instance_id="gpt-4")
    result = llm_helper.process_prompt(prompt, context)
    return result.dict()
```

### **2. Service Dependencies → Direct Library Calls**

**BEFORE:**
```python
# HTTP call to Prompt Studio service
response = requests.post("http://prompt-service/api/extract", {
    "document_path": path,
    "config": settings
})
```

**AFTER:**
```python
# Direct helper function call
from unstract.prompt_helpers import ExtractionHelper

extraction_helper = ExtractionHelper(config)
result = extraction_helper.extract_text_from_file(path)
```

### **3. Flask Routes → Workflow Tasks**

**BEFORE:**
```python
# prompt-service/controllers/extraction.py
@extraction_bp.route("/extract", methods=["POST"])
def extract():
    # Route logic
    return result
```

**AFTER:**
```python
# Workflow task
@task(name="extract-text")
def extract_text(self, input_data, ctx):
    helper = ExtractionHelper()
    return helper.extract_text_from_file(input_data["path"])
```

## 🔄 **Migration Strategy**

### **Phase 1: Create Helper Library (Week 1-2)**

1. **Extract Core Logic**
   ```bash
   # Create helper package
   mkdir -p unstract/prompt-helpers/src/unstract/prompt_helpers
   
   # Extract modules from prompt-service
   # - LLM interaction logic
   # - Text extraction utilities
   # - Chunking and embedding logic
   # - Evaluation functions
   # - Formatting utilities
   ```

2. **Remove Dependencies**
   - Extract Django model dependencies
   - Remove Flask-specific code
   - Create pure functions with clear interfaces
   - Add comprehensive type hints and validation

3. **Package Structure**
   ```
   unstract/prompt-helpers/
   ├── src/unstract/prompt_helpers/
   │   ├── __init__.py           # Main exports
   │   ├── models.py             # Pydantic models
   │   ├── llm.py               # LLM interaction helpers
   │   ├── extraction.py        # Text extraction helpers
   │   ├── chunking.py          # Text chunking utilities
   │   ├── embedding.py         # Vector embedding helpers
   │   ├── evaluation.py        # Result evaluation helpers
   │   ├── formatting.py        # Output formatting helpers
   │   └── rag.py              # RAG processing helpers
   ```

### **Phase 2: Update Workflows (Week 2-3)**

1. **Redesign Workflow Tasks**
   ```python
   # OLD: Service call
   @task(name="process-llm")
   def process_llm(self, input_data, ctx):
       response = requests.post("http://prompt-service/api/process", data)
       return response.json()
   
   # NEW: Helper function call
   @task(name="process-llm") 
   def process_llm(self, input_data, ctx):
       llm_helper = LLMHelper(adapter_instance_id=input_data["llm_id"])
       result = llm_helper.process_prompt(input_data["prompt"], input_data["context"])
       return result.dict()
   ```

2. **Update Existing Workflows**
   - Replace service calls with helper calls
   - Add proper error handling
   - Update input/output models
   - Test individual helper functions

### **Phase 3: Backend Integration (Week 3-4)**

1. **Update Django Backend**
   ```python
   # OLD: Call Prompt Studio service
   def trigger_processing(request):
       response = requests.post("http://prompt-service/api/process", payload)
       return JsonResponse(response.json())
   
   # NEW: Trigger workflow
   def trigger_processing(request):
       client = get_task_client()
       result = await client.run_workflow("document-processing", request.json())
       return JsonResponse({"workflow_id": result.workflow_id})
   ```

2. **Remove Service References**
   - Update Docker Compose configurations
   - Remove prompt-service containers
   - Update environment variables
   - Update service discovery configurations

### **Phase 4: Deployment & Cleanup (Week 4-5)**

1. **Deploy New Architecture**
   - Update Kubernetes/Docker configurations
   - Remove Prompt Studio service deployments
   - Update load balancer configurations
   - Update monitoring and alerting

2. **Clean Up Codebase**
   - Remove `prompt-service/` directory
   - Update documentation
   - Remove unused dependencies
   - Update API documentation

## 💡 **Benefits of Service Consolidation**

### **1. Simplified Architecture**
- **Reduced Complexity**: Fewer services to manage and deploy
- **Eliminated HTTP Overhead**: Direct function calls vs service-to-service HTTP requests  
- **Simplified Debugging**: Single process tracing vs distributed debugging
- **Reduced Latency**: No network calls for prompt processing

### **2. Improved Maintainability**
- **Single Codebase**: Helper functions in one package vs distributed service logic
- **Easier Testing**: Unit test helpers vs integration test services
- **Clear Interfaces**: Typed function signatures vs HTTP API contracts
- **Reduced Coupling**: No Django dependencies in helpers

### **3. Enhanced Performance**
- **No Network Latency**: Direct function calls
- **Memory Efficiency**: Shared process memory vs separate service memory
- **Resource Optimization**: One set of LLM adapters vs multiple service instances
- **Faster Development**: No service restart for helper changes

### **4. Operational Benefits**
- **Fewer Deployments**: One less service to deploy and manage
- **Simplified Monitoring**: Fewer service health checks and metrics
- **Reduced Infrastructure**: Less CPU/memory/network overhead
- **Easier Scaling**: Scale workflows vs scaling multiple services

## 🔍 **Implementation Details**

### **Helper Function Design Patterns**

1. **Stateless Functions**
   ```python
   # Pure function with clear inputs/outputs
   def extract_text_from_file(file_path: str, config: ExtractionConfig) -> ExtractionResult:
       # No global state, no side effects
       return ExtractionResult(...)
   ```

2. **Configuration-Driven**
   ```python
   # Pydantic configuration models
   class LLMConfig(BaseModel):
       adapter_instance_id: str
       temperature: float = 0.1
       max_tokens: int = 4000
   ```

3. **Error Handling**
   ```python
   # Comprehensive error handling with structured results
   try:
       result = helper.process()
       result.mark_completed()
       return result
   except Exception as e:
       result.mark_failed(str(e))
       return result
   ```

4. **Type Safety**
   ```python
   # Full type hints and Pydantic validation
   def process_prompt(
       self,
       prompt: str,
       context: Optional[Dict[str, Any]] = None,
       workflow_context: Optional[WorkflowContext] = None
   ) -> LLMProcessingResult:
   ```

### **Testing Strategy**

1. **Unit Testing Helpers**
   ```python
   def test_llm_helper():
       helper = LLMHelper("test-adapter")
       result = helper.process_prompt("test prompt")
       assert result.status == ProcessingStatus.COMPLETED
   ```

2. **Integration Testing Workflows**
   ```python
   async def test_document_workflow():
       client = get_task_client(backend_override="celery")  # Test backend
       result = await client.run_workflow("document-processing", test_data)
       assert result.status == WorkflowStatus.COMPLETED
   ```

3. **Performance Testing**
   ```python
   def test_helper_performance():
       # Compare helper vs service call performance
       helper_time = time_helper_call()
       service_time = time_service_call()  
       assert helper_time < service_time * 0.5  # 50% faster
   ```

### **Migration Validation**

1. **Functional Equivalence**
   - All Prompt Studio endpoints have workflow equivalents
   - Same input/output formats maintained
   - Error handling patterns preserved
   - Performance characteristics maintained or improved

2. **API Compatibility**
   ```python
   # Maintain backward compatibility during migration
   @app.route("/api/v1/process", methods=["POST"])  # Legacy
   def legacy_process():
       # Redirect to workflow
       return trigger_workflow(request.json())
   
   @app.route("/api/v2/process", methods=["POST"])  # New
   async def new_process():
       # Direct workflow execution
       result = await client.run_workflow("processing", request.json())
       return jsonify(result.dict())
   ```

3. **Performance Validation**
   - Response time improvements (target: 30% faster)
   - Resource usage reduction (target: 40% less memory)
   - Error rate maintenance (target: same or better)
   - Throughput improvements (target: 2x concurrent processing)

## 🎯 **Success Metrics**

### **Technical Metrics**
- **Services Reduced**: 1 fewer service (Prompt Studio eliminated)
- **Code Complexity**: 60% reduction in service integration code
- **Response Time**: 30% improvement in processing latency  
- **Resource Usage**: 40% reduction in total memory footprint
- **Error Rate**: Maintained or improved error handling

### **Operational Metrics**
- **Deployment Simplicity**: 50% faster deployment cycles
- **Development Velocity**: 40% faster feature development
- **Debugging Time**: 70% faster issue resolution
- **Maintenance Overhead**: 60% reduction in service management tasks

### **Developer Experience**
- **Learning Curve**: Simpler helper functions vs complex service APIs
- **Testing**: Unit testable functions vs integration test services
- **Local Development**: No service dependencies for helper development
- **Code Reuse**: Helpers usable across multiple workflows/services

## 🚀 **Deployment Plan**

### **Week 1-2: Helper Library Development**
- [ ] Extract core Prompt Studio logic into helpers
- [ ] Remove Django/Flask dependencies  
- [ ] Add comprehensive type hints and Pydantic models
- [ ] Create unit tests for all helper functions
- [ ] Package and publish helper library

### **Week 2-3: Workflow Migration**
- [ ] Update existing workflows to use helpers
- [ ] Replace service calls with helper function calls
- [ ] Update workflow input/output models
- [ ] Test workflow execution with helpers
- [ ] Performance benchmark helper vs service calls

### **Week 3-4: Backend Integration**
- [ ] Update Django backend to trigger workflows
- [ ] Remove Prompt Studio service references
- [ ] Update API endpoints to use workflows
- [ ] Create backward compatibility layer
- [ ] Update monitoring and logging

### **Week 4-5: Deployment & Cleanup**
- [ ] Deploy new architecture to staging
- [ ] Performance and load testing
- [ ] Deploy to production
- [ ] Remove Prompt Studio service containers
- [ ] Clean up codebase and documentation
- [ ] Monitor performance and error rates

## 🎉 **Expected Outcomes**

This service consolidation strategy will result in:

1. **Simplified Architecture**: One fewer service to manage
2. **Improved Performance**: Direct function calls vs HTTP service calls  
3. **Better Developer Experience**: Testable helpers vs complex service integration
4. **Reduced Operational Overhead**: Fewer deployments and monitoring points
5. **Enhanced Maintainability**: Single codebase vs distributed service logic

The elimination of Prompt Studio service while maintaining all functionality represents a **significant architectural improvement** that aligns with modern microservice consolidation best practices.

**Next Steps**: Begin Phase 1 by extracting core Prompt Studio logic into the helper library package structure already created.