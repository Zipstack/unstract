# Vibe Extractor Service

The Vibe Extractor Service is an agentic system that automatically generates document extraction metadata, fields, and prompts using LLM technology. It follows the architecture and patterns from the `new_document_type_generator.py` reference implementation.

## Overview

This service generates all the necessary components for document extraction:
- Document metadata (metadata.yaml)
- Extraction fields (extraction.yaml)
- Page extraction prompts (system and user)
- Scalar extraction prompts (system and user)
- Table extraction prompts (system and user)

## Architecture

### Components

```
vibe_extractor/
├── __init__.py              # Package exports
├── constants.py             # Bootstrap prompts and constants
├── llm_helper.py           # LLM client initialization (using autogen-ext)
├── generator.py            # Core generation logic
├── service.py              # Service orchestration
├── api_helper.py           # API integration helpers
└── README.md               # This file
```

### LLM Adapter Pattern

The service uses the autogen-ext library for LLM communication, making it easy to swap between different providers:

- **OpenAI**: Standard OpenAI models
- **Azure OpenAI**: Azure-hosted OpenAI models
- **Anthropic**: Claude models
- **Bedrock**: AWS Bedrock with Claude models

This architecture is designed to be easily replaceable with the new autogen client when it becomes available.

## Usage

### Basic Usage

```python
from unstract.prompt_service.services.vibe_extractor.api_helper import (
    generate_document_extraction_components
)

# Configure LLM
llm_config = {
    "adapter_id": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "api_key": "sk-ant-...",
    "temperature": 0.7,
    "max_tokens": 4096
}

# Generate all components
result = await generate_document_extraction_components(
    doc_type="invoice",
    output_dir="/path/to/output",
    llm_config=llm_config
)

if result["status"] == "success":
    print(f"Generated files at: {result['output_path']}")
    print(f"Files: {result['files']}")
else:
    print(f"Error: {result['error']}")
```

### Backend Integration

The backend integrates with this service through the `GeneratorService` class:

```python
from prompt_studio.prompt_studio_vibe_extractor_v2.services.generator_service import (
    GeneratorService
)

# Generate all components for a project
result = GeneratorService.generate_all(project)
```

## Configuration

### Environment Variables

For the backend to use this service, configure these environment variables:

```bash
# LLM Provider Configuration
VIBE_EXTRACTOR_ADAPTER_ID=anthropic  # or openai, azureopenai, bedrock
VIBE_EXTRACTOR_MODEL=claude-3-5-sonnet-20241022
VIBE_EXTRACTOR_API_KEY=your-api-key-here
VIBE_EXTRACTOR_TEMPERATURE=0.7
VIBE_EXTRACTOR_MAX_TOKENS=4096

# For Azure OpenAI
VIBE_EXTRACTOR_API_BASE=https://your-resource.openai.azure.com/
VIBE_EXTRACTOR_API_VERSION=2024-02-15-preview
VIBE_EXTRACTOR_DEPLOYMENT=your-deployment-name

# For AWS Bedrock
VIBE_EXTRACTOR_AWS_ACCESS_KEY_ID=your-access-key
VIBE_EXTRACTOR_AWS_SECRET_ACCESS_KEY=your-secret-key
VIBE_EXTRACTOR_REGION_NAME=us-east-1
```

### Django Settings

Alternatively, configure in Django settings.py:

```python
VIBE_EXTRACTOR_LLM_CONFIG = {
    "adapter_id": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "api_key": os.environ.get("ANTHROPIC_API_KEY"),
    "temperature": 0.7,
    "max_tokens": 4096,
}
```

## API Endpoints

### Backend API Endpoints

#### Create Project
```http
POST /api/v1/vibe-extractor/
Content-Type: application/json

{
  "document_type": "invoice",
  "tool_id": "optional-tool-uuid"
}
```

#### Generate Components
```http
POST /api/v1/vibe-extractor/{project_id}/generate/
Content-Type: application/json

{
  "regenerate": false
}
```

Response:
```json
{
  "message": "Generation started",
  "project_id": "uuid",
  "status": "generating_metadata"
}
```

#### Read Generated File
```http
GET /api/v1/vibe-extractor/{project_id}/read_file/?file_type=metadata
```

Response:
```json
{
  "file_type": "metadata",
  "content": "...",
  "project_id": "uuid"
}
```

Supported file types:
- `metadata`: metadata.yaml
- `extraction`: extraction.yaml
- `page_extraction_system`: Page extraction system prompt
- `page_extraction_user`: Page extraction user prompt
- `scalars_extraction_system`: Scalar extraction system prompt
- `scalars_extraction_user`: Scalar extraction user prompt
- `tables_extraction_system`: Table extraction system prompt
- `tables_extraction_user`: Table extraction user prompt

#### List Generated Files
```http
GET /api/v1/vibe-extractor/{project_id}/list_files/
```

Response:
```json
{
  "project_id": "uuid",
  "files": [
    {"file_type": "metadata", "exists": true},
    {"file_type": "extraction", "exists": true},
    ...
  ]
}
```

## Generation Steps

The service generates components in the following sequence:

1. **Generate Metadata** (`generating_metadata`)
   - Creates metadata.yaml with document type information
   - Includes name, description, tags, version, etc.

2. **Generate Extraction Fields** (`generating_fields`)
   - Creates extraction.yaml with field definitions
   - Includes scalar fields and list/table fields

3. **Generate Page Extraction Prompts** (`generating_prompts`)
   - System prompt for page relevance detection
   - User prompt for page analysis

4. **Generate Scalar Extraction Prompts**
   - System prompt for scalar field extraction
   - User prompt for scalar extraction

5. **Generate Table Extraction Prompts**
   - System prompt for table/list extraction
   - User prompt for table extraction

Each step updates the project status and progress tracking.

## Progress Tracking

The service provides progress callbacks to track generation:

```python
def progress_callback(step: str, status: str, message: str = ""):
    print(f"Step: {step}, Status: {status}, Message: {message}")

result = await service.generate_all(
    doc_type="invoice",
    reference_template=template,
    progress_callback=progress_callback
)
```

## Error Handling

The service includes comprehensive error handling:

- Invalid LLM configuration
- API failures
- File I/O errors
- Invalid document types
- Generation failures

All errors are logged and returned with descriptive messages.

## Testing

### Manual Testing

1. Create a project:
```bash
curl -X POST http://localhost:8000/api/v1/vibe-extractor/ \
  -H "Content-Type: application/json" \
  -d '{"document_type": "invoice"}'
```

2. Start generation:
```bash
curl -X POST http://localhost:8000/api/v1/vibe-extractor/{project_id}/generate/ \
  -H "Content-Type: application/json" \
  -d '{}'
```

3. Check status:
```bash
curl http://localhost:8000/api/v1/vibe-extractor/{project_id}/
```

4. Read generated files:
```bash
curl http://localhost:8000/api/v1/vibe-extractor/{project_id}/read_file/?file_type=metadata
```

## Future Enhancements

### Autogen Client Migration

The current implementation uses autogen-ext for LLM communication. When the new autogen client is ready, migration will be straightforward:

1. Update `llm_helper.py` to use the new autogen client
2. Update `generate_with_llm()` function
3. No changes needed in `generator.py` or `service.py`

### Celery Integration

For production deployments, replace the threading-based background processing with Celery:

```python
from celery import shared_task

@shared_task
def generate_components_task(project_id):
    project = VibeExtractorProject.objects.get(project_id=project_id)
    return GeneratorService.generate_all(project)
```

### Caching

Add caching for reference templates and frequently used prompts to improve performance.

## Troubleshooting

### Import Errors

If you see import errors, ensure the prompt-service is properly installed:
```bash
cd prompt-service
pip install -e .
```

### LLM Configuration Errors

Verify your LLM configuration:
```python
from unstract.prompt_service.services.vibe_extractor.api_helper import (
    validate_llm_config
)

is_valid, error = validate_llm_config(llm_config)
if not is_valid:
    print(f"Configuration error: {error}")
```

### Generation Failures

Check the logs for detailed error messages:
```bash
tail -f /path/to/logs/django.log
```

## Code Style

The implementation follows Unstract coding standards:
- Type hints for all function parameters and returns
- Comprehensive docstrings
- Error handling and logging
- Consistent naming conventions
- Clean separation of concerns

## References

- Reference Implementation: `/home/harini/Documents/Workspace/unstract-omniparse-studio/tools/new_document_type_generator.py`
- Rentroll Service (Adapter Pattern): `/home/harini/Documents/Workspace/unstract-cloud/rentroll-service/`
- Backend Models: `backend/prompt_studio/prompt_studio_vibe_extractor_v2/models.py`
