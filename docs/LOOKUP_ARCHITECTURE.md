# Lookup System - Architecture Documentation

## Profile-Based Adapter System (Aligned with Prompt Studio)

**Last Updated**: 2025-02-05
**Status**: Implemented
**Based On**: Prompt Studio's ProfileManager pattern

---

## Executive Summary

The Lookup system enables **reference data enrichment** in document extraction workflows. Users upload reference data (CSV, JSON, PDF), which is indexed into a vector database. During prompt execution, extracted values are matched against reference data to provide standardized/enriched values.

### Key Features

1. **LookupProject** - Container for lookup configurations and reference data
2. **LookupProfileManager** - Adapter configurations (X2Text, Embedding, VectorDB, LLM)
3. **LookupDataSource** - Reference data file storage with version management
4. **LookupIndexManager** - Vector DB index tracking with reindex capabilities
5. **PromptStudioLookupLink** - Links Prompt Studio prompts to Lookup projects
6. **LookupExecutionAudit** - Comprehensive execution logging

---

## Data Models

### LookupProject

Container for a lookup configuration with LLM settings and organization association.

```python
class LookupProject(DefaultOrganizationMixin, BaseModel):
    """Represents a Look-Up project for static data-based enrichment."""

    LOOKUP_TYPE_CHOICES = [("static_data", "Static Data")]
    LLM_PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("azure", "Azure OpenAI"),
        ("custom", "Custom Provider"),
    ]

    id = UUIDField(primary_key=True)
    name = CharField(max_length=255)
    description = TextField(blank=True, null=True)
    lookup_type = CharField(choices=LOOKUP_TYPE_CHOICES, default="static_data")

    # Template and status
    template = ForeignKey("LookupPromptTemplate", SET_NULL, null=True)
    is_active = BooleanField(default=True)
    metadata = JSONField(default=dict)

    # LLM Configuration
    llm_provider = CharField(choices=LLM_PROVIDER_CHOICES, null=True)
    llm_model = CharField(max_length=100, null=True)
    llm_config = JSONField(default=dict)

    # Ownership
    created_by = ForeignKey(User, RESTRICT)

    class Meta:
        db_table = "lookup_projects"

    @property
    def is_ready(self) -> bool:
        """Check if project has completed reference data."""
        ...
```

### LookupProfileManager

Profile manager for adapter configurations - mirrors Prompt Studio's ProfileManager.

```python
class LookupProfileManager(BaseModel):
    """Model to store adapter configuration profiles for Look-Up projects."""

    profile_id = UUIDField(primary_key=True)
    profile_name = TextField(blank=False, null=False)

    # Foreign key to LookupProject
    lookup_project = ForeignKey("LookupProject", CASCADE, related_name="profiles")

    # Required Adapters - All must be configured
    vector_store = ForeignKey(AdapterInstance, PROTECT, related_name="lookup_profiles_vector_store")
    embedding_model = ForeignKey(AdapterInstance, PROTECT, related_name="lookup_profiles_embedding_model")
    llm = ForeignKey(AdapterInstance, PROTECT, related_name="lookup_profiles_llm")
    x2text = ForeignKey(AdapterInstance, PROTECT, related_name="lookup_profiles_x2text")

    # Configuration fields
    chunk_size = IntegerField(default=1000)
    chunk_overlap = IntegerField(default=200)
    similarity_top_k = IntegerField(default=5)

    # Flags
    is_default = BooleanField(default=False)
    reindex = BooleanField(default=False)

    # Audit
    created_by = ForeignKey(User, SET_NULL, null=True)
    modified_by = ForeignKey(User, SET_NULL, null=True)

    class Meta:
        db_table = "lookup_profile_manager"
        constraints = [
            UniqueConstraint(fields=["lookup_project", "profile_name"])
        ]

    @staticmethod
    def get_default_profile(project) -> "LookupProfileManager":
        """Get default profile for a Look-Up project."""
        ...
```

### LookupDataSource

Reference data file storage with automatic version management.

```python
class LookupDataSource(BaseModel):
    """Represents a reference data source with version management."""

    EXTRACTION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    FILE_TYPE_CHOICES = [
        ("pdf", "PDF"), ("xlsx", "Excel"), ("csv", "CSV"),
        ("docx", "Word"), ("txt", "Text"), ("json", "JSON"),
    ]

    id = UUIDField(primary_key=True)
    project = ForeignKey("LookupProject", CASCADE, related_name="data_sources")

    # File Information
    file_name = CharField(max_length=255)
    file_path = TextField()  # Path in object storage (MinIO)
    file_size = BigIntegerField()
    file_type = CharField(choices=FILE_TYPE_CHOICES)

    # Extracted Content
    extracted_content_path = TextField(blank=True, null=True)
    extraction_status = CharField(choices=EXTRACTION_STATUS_CHOICES, default="pending")
    extraction_error = TextField(blank=True, null=True)

    # Version Management (auto-managed via signals)
    version_number = IntegerField(default=1)
    is_latest = BooleanField(default=True)

    # Upload Information
    uploaded_by = ForeignKey(User, RESTRICT)

    class Meta:
        db_table = "lookup_data_sources"
        unique_together = [["project", "version_number"]]
```

**Version Management Signals:**
- `pre_save`: Auto-increments version number, marks previous versions as not latest
- `post_delete`: Promotes previous version to latest when current latest is deleted

### LookupIndexManager

Tracks indexed reference data in Vector DB.

```python
class LookupIndexManager(BaseModel):
    """Model to store indexing details for Look-Up reference data."""

    index_manager_id = UUIDField(primary_key=True)

    # References
    data_source = ForeignKey("LookupDataSource", CASCADE, related_name="index_managers")
    profile_manager = ForeignKey("LookupProfileManager", SET_NULL, null=True, related_name="index_managers")

    # Vector DB index ID
    raw_index_id = CharField(max_length=255, null=True)
    index_ids_history = JSONField(default=list)  # For cleanup on deletion

    # Status tracking
    extraction_status = JSONField(default=dict)  # Per X2Text config
    status = JSONField(default=dict)  # Legacy: {extracted, indexed, error}
    reindex_required = BooleanField(default=False)

    # Audit
    created_by = ForeignKey(User, SET_NULL, null=True)
    modified_by = ForeignKey(User, SET_NULL, null=True)

    class Meta:
        db_table = "lookup_index_manager"
        constraints = [
            UniqueConstraint(fields=["data_source", "profile_manager"])
        ]
```

**Cleanup Signal:**
- `pre_delete`: Cleans up vector DB entries when index manager is deleted

### PromptStudioLookupLink

Many-to-many relationship between Prompt Studio projects and Look-Up projects.

```python
class PromptStudioLookupLink(Model):
    """Links Prompt Studio projects with Look-Up projects."""

    id = UUIDField(primary_key=True)
    prompt_studio_project_id = UUIDField()  # PS project reference
    lookup_project = ForeignKey("LookupProject", CASCADE, related_name="ps_links")
    execution_order = PositiveIntegerField(default=0)
    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "prompt_studio_lookup_links"
        unique_together = [["prompt_studio_project_id", "lookup_project"]]
```

### LookupPromptTemplate

Prompt template with variable detection and validation.

```python
class LookupPromptTemplate(BaseModel):
    """Represents a prompt template with {{variable}} placeholders."""

    VARIABLE_PATTERN = r"\{\{([^}]+)\}\}"

    id = UUIDField(primary_key=True)
    project = OneToOneField("LookupProject", CASCADE, related_name="prompt_template_link")

    name = CharField(max_length=255)
    template_text = TextField()  # Contains {{variable}} placeholders
    llm_config = JSONField(default=dict)
    is_active = BooleanField(default=True)
    created_by = ForeignKey(User, RESTRICT)
    variable_mappings = JSONField(default=dict)

    class Meta:
        db_table = "lookup_prompt_templates"

    def detect_variables(self) -> list[str]:
        """Extract all {{variable}} references from template."""
        ...

    def validate_syntax(self) -> bool:
        """Validate matching braces and no nested placeholders."""
        ...
```

### LookupExecutionAudit

Comprehensive audit log for Look-Up executions.

```python
class LookupExecutionAudit(Model):
    """Audit log for Look-Up executions."""

    STATUS_CHOICES = [
        ("success", "Success"),
        ("partial", "Partial Success"),
        ("failed", "Failed"),
    ]

    id = UUIDField(primary_key=True)

    # Execution Context
    lookup_project = ForeignKey("LookupProject", CASCADE, related_name="execution_audits")
    prompt_studio_project_id = UUIDField(null=True)
    execution_id = UUIDField()  # Groups all Look-Ups in a batch
    file_execution_id = UUIDField(null=True)  # Workflow tracking for API/ETL

    # Input/Output
    input_data = JSONField()
    reference_data_version = IntegerField()
    enriched_output = JSONField(null=True)

    # LLM Details
    llm_provider = CharField(max_length=50)
    llm_model = CharField(max_length=100)
    llm_prompt = TextField()
    llm_response = TextField(null=True)
    llm_response_cached = BooleanField(default=False)

    # Performance Metrics
    execution_time_ms = IntegerField(null=True)
    llm_call_time_ms = IntegerField(null=True)

    # Status & Errors
    status = CharField(choices=STATUS_CHOICES)
    error_message = TextField(null=True)
    confidence_score = DecimalField(max_digits=3, decimal_places=2, null=True)

    executed_at = DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lookup_execution_audit"
```

---

## Service Layer

### Core Services

| Service | Purpose |
|---------|---------|
| `IndexingService` | Document indexing with chunking and vector embeddings |
| `LookUpExecutor` | Executes lookups using RAG retrieval |
| `LookUpOrchestrator` | Coordinates lookup workflow orchestration |
| `LookupRetrievalService` | Vector DB search and retrieval |
| `VectorDBCleanupService` | Manages vector DB lifecycle and cleanup |

### Supporting Services

| Service | Purpose |
|---------|---------|
| `AuditLogger` | Execution logging and audit trail |
| `LLMResponseCache` | Caches LLM responses for performance |
| `ReferenceDataLoader` | Loads and parses reference data files |
| `VariableResolver` | Resolves template variables with actual values |
| `EnrichmentMerger` | Merges lookup results into extraction output |
| `LookupIndexHelper` | Helper functions for index operations |
| `LogEmitter` | Emits logs for execution tracking |

### Integration Services

| Service | Purpose |
|---------|---------|
| `LookupDocumentIndexingService` | High-level document indexing orchestration |
| `LookupIntegrationService` | Integration with external systems |
| `WorkflowIntegration` | Integration with workflow execution |

---

## API Endpoints

Base URL: `/api/v2/unstract/{org_id}/lookup/`

### Project Management

```
GET    /lookup-projects/                 # List all projects
POST   /lookup-projects/                 # Create new project
GET    /lookup-projects/{id}/            # Get project details
PUT    /lookup-projects/{id}/            # Update project
DELETE /lookup-projects/{id}/            # Delete project
```

### Profile Management

```
GET    /lookup-profiles/                 # List profiles
POST   /lookup-profiles/                 # Create profile
GET    /lookup-profiles/{id}/            # Get profile details
PUT    /lookup-profiles/{id}/            # Update profile
DELETE /lookup-profiles/{id}/            # Delete profile
POST   /lookup-profiles/{id}/set-default/ # Set as default profile
```

### Data Source Management

```
GET    /data-sources/                    # List data sources
POST   /data-sources/                    # Upload new reference data
GET    /data-sources/{id}/               # Get data source details
DELETE /data-sources/{id}/               # Delete data source
POST   /data-sources/{id}/reindex/       # Trigger reindexing
```

### Template Management

```
GET    /lookup-templates/                # List templates
POST   /lookup-templates/                # Create template
GET    /lookup-templates/{id}/           # Get template details
PUT    /lookup-templates/{id}/           # Update template
DELETE /lookup-templates/{id}/           # Delete template
```

### Linking & Execution

```
GET    /lookup-links/                    # List PS project links
POST   /lookup-links/                    # Create link
DELETE /lookup-links/{id}/               # Remove link

GET    /execution-audits/                # List execution history
GET    /execution-audits/{id}/           # Get execution details

POST   /lookup-debug/test/               # Test lookup execution
```

---

## Frontend Components

### Page Structure

```
/lookups                          → LookUpProjectList
/lookups/:projectId               → LookUpProjectDetail
    ├── Reference Data Tab        → ReferenceDataTab
    ├── Templates Tab             → TemplateTab
    ├── Profiles Tab              → ProfileManagementTab
    │   └── Profile Modal         → ProfileFormModal
    ├── Linked Projects Tab       → LinkedProjectsTab
    ├── Execution History Tab     → ExecutionHistoryTab
    └── Debug Tab                 → DebugTab
```

### Component Descriptions

| Component | Purpose |
|-----------|---------|
| `LookUpProjectList` | Lists all lookup projects with create/delete actions |
| `LookUpProjectDetail` | Project detail view with tabbed navigation |
| `CreateProjectModal` | Modal for creating new lookup projects |
| `ReferenceDataTab` | Upload and manage reference data files |
| `TemplateTab` | Configure prompt templates with variables |
| `ProfileManagementTab` | Manage adapter profiles |
| `ProfileFormModal` | Create/edit profiles with adapter dropdowns |
| `LinkedProjectsTab` | Link/unlink Prompt Studio projects |
| `ExecutionHistoryTab` | View execution audit logs |
| `DebugTab` | Test lookup execution manually |

---

## System Workflows

### 1. Reference Data Indexing Workflow

```
User uploads reference file (CSV/JSON/PDF)
    ↓
Create LookupDataSource (version auto-incremented)
    ↓
Get default LookupProfileManager for project
    ↓
Extract text using profile.x2text adapter
    ↓
Store extracted text in MinIO
    ↓
Chunk text (profile.chunk_size, profile.chunk_overlap)
    ↓
Generate embeddings using profile.embedding_model
    ↓
Store vectors in VectorDB using profile.vector_store
    ↓
Create/update LookupIndexManager entry
    ↓
Update data source status to 'completed'
```

### 2. Lookup Execution Workflow

```
Prompt Studio executes with lookup variable
    ↓
Get linked LookupProject via PromptStudioLookupLink
    ↓
Get default profile (LookupProfileManager.get_default_profile)
    ↓
Generate query embedding using profile.embedding_model
    ↓
Search VectorDB using profile.vector_store
    (returns top_k similar results based on profile.similarity_top_k)
    ↓
Optional: Use profile.llm for best match selection
    ↓
Create LookupExecutionAudit record
    ↓
Return standardized value to Prompt Studio
```

### 3. Profile Change & Reindexing Workflow

```
User updates profile settings (chunk_size, adapters, etc.)
    ↓
Set reindex_required=True on associated LookupIndexManager entries
    ↓
User triggers reindex (or automatic reindex on next execution)
    ↓
Delete old vector DB indexes (using index_ids_history)
    ↓
Re-run indexing workflow with new profile settings
    ↓
Update LookupIndexManager with new index IDs
    ↓
Set reindex_required=False
```

### 4. Cleanup Workflows

**On LookupDataSource deletion:**
```
Cascade delete LookupIndexManager entries
    ↓
pre_delete signal on LookupIndexManager
    ↓
VectorDBCleanupService.cleanup_index_ids()
    ↓
Remove vectors from VectorDB
```

**On LookupProfileManager deletion:**
```
pre_delete signal on LookupProfileManager
    ↓
For each associated LookupIndexManager:
    ↓
VectorDBCleanupService.cleanup_index_ids()
    ↓
Remove all vectors indexed with this profile
```

---

## Integration with Prompt Studio

### Prompt-Level Lookup Configuration

The `ToolStudioPrompt` model has been extended with a `lookup_project` field:

```python
class ToolStudioPrompt(BaseModel):
    # ... existing fields ...

    lookup_project = ForeignKey(
        "lookup.LookupProject",
        on_delete=SET_NULL,
        null=True,
        blank=True,
        related_name="linked_prompts",
    )
```

### Frontend Integration

- **Lookup Replacement Indicator**: Visual indicator on prompts with lookup configured
- **Prompt Card Header**: Shows lookup project linkage
- **Output Display**: Shows lookup-enriched values in combined output

---

## Database Tables

| Table | Description |
|-------|-------------|
| `lookup_projects` | Lookup project configurations |
| `lookup_data_sources` | Reference data file metadata |
| `lookup_profile_manager` | Adapter profile configurations |
| `lookup_index_manager` | Vector DB index tracking |
| `lookup_prompt_templates` | Prompt templates with variables |
| `prompt_studio_lookup_links` | PS-to-Lookup project links |
| `lookup_execution_audit` | Execution history and metrics |

---

## Key Design Principles

### 1. Consistency with Prompt Studio
- Same model structure (FK to project, unique constraint on name)
- Same adapter fields (x2text, embedding_model, vector_store, llm)
- Same naming conventions (ProfileManager, is_default, reindex)
- Same API patterns (ViewSet, Serializer, permissions)

### 2. Profile Ownership
- Profiles belong to projects (not standalone)
- Each project can have multiple profiles
- One profile must be marked as default
- Unique profile names within a project

### 3. Adapter Protection
- All 4 adapter types required for completeness
- Adapters protected from deletion if in use (PROTECT)
- Users select from configured adapters via dropdowns

### 4. Separation of Concerns
- **LookupProfileManager**: Adapter configuration storage
- **LookupIndexManager**: Indexing state tracking
- **LookupDataSource**: Reference data file metadata
- **LookUpExecutor**: Runtime execution logic

### 5. Automatic Cleanup
- Vector DB cleanup on index/profile deletion via signals
- Index history tracking for complete cleanup
- Version promotion on data source deletion

### 6. Comprehensive Auditing
- LookupExecutionAudit captures all execution details
- file_execution_id for workflow tracking in API/ETL
- LLM prompts, responses, and performance metrics logged

---

## Environment Configuration

The lookup system uses existing adapter configurations. No new environment variables required.

**Used Configuration:**
- MinIO/S3 for file storage (via existing filesystem configuration)
- Redis for caching (via existing Redis configuration)
- Existing adapter instances for X2Text, Embedding, VectorDB, LLM

---

## Testing

### Unit Tests Location

```
backend/lookup/tests/
├── test_api/
│   ├── test_execution_api.py
│   ├── test_linking_api.py
│   ├── test_profile_manager_api.py
│   ├── test_project_api.py
│   └── test_template_api.py
├── test_integrations/
│   ├── test_llm_integration.py
│   ├── test_llmwhisperer_integration.py
│   ├── test_redis_cache_integration.py
│   └── test_storage_integration.py
├── test_services/
│   ├── test_audit_logger.py
│   ├── test_enrichment_merger.py
│   ├── test_llm_cache.py
│   ├── test_lookup_executor.py
│   ├── test_lookup_orchestrator.py
│   └── test_reference_data_loader.py
├── test_migrations.py
└── test_variable_resolver.py
```

### Test Coverage Areas
- Model CRUD operations
- API endpoint functionality
- Service layer logic
- Integration with adapters
- Vector DB cleanup signals
- Version management
- Cache operations

---

**END OF ARCHITECTURE DOCUMENT**
