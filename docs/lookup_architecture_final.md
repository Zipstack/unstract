# Lookup System - Final Architecture
## Profile-Based Adapter System (Aligned with Prompt Studio)

**Date**: 2025-12-26
**Status**: Current Architecture Specification
**Based On**: Prompt Studio's ProfileManager pattern

---

## Executive Summary

The Lookup system uses a **profile-based architecture** identical to Prompt Studio's approach:

1. **LookupProfileManager** - Separate entity storing adapter configurations
2. **Profile Linking** - Each LookupProject links to multiple profiles (one default)
3. **Adapter Selection** - Users choose adapters via dropdowns (like Templates screen)
4. **Profile Screen** - Separate UI for managing profiles per project
5. **Unified Pattern** - Same adapter system (X2Text, Embedding, VectorDB, LLM)

---

## Architecture Alignment with Prompt Studio

### Prompt Studio Pattern (Reference)

```python
class ProfileManager(BaseModel):
    profile_id = UUIDField(primary_key=True)
    profile_name = TextField(blank=False)

    # FK to Project/Tool
    prompt_studio_tool = FK(CustomTool, on_delete=CASCADE)

    # Required Adapters
    vector_store = FK(AdapterInstance, blank=False, null=False)
    embedding_model = FK(AdapterInstance, blank=False, null=False)
    llm = FK(AdapterInstance, blank=False, null=False)
    x2text = FK(AdapterInstance, blank=False, null=False)

    # Configuration
    chunk_size = IntegerField(null=True, blank=True)
    chunk_overlap = IntegerField(null=True, blank=True)
    retrieval_strategy = TextField(choices=...)
    similarity_top_k = IntegerField(blank=True, null=True)

    # Flags
    is_default = BooleanField(default=False)
    reindex = BooleanField(default=False)

    # Unique constraint
    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["prompt_studio_tool", "profile_name"],
                name="unique_prompt_studio_tool_profile_name_index"
            )
        ]
```

### Lookup System Pattern (New)

```python
class LookupProfileManager(BaseModel):
    """Profile manager for Lookup projects - mirrors Prompt Studio's ProfileManager."""

    profile_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    profile_name = models.TextField(
        blank=False,
        null=False,
        db_comment="Name of the lookup profile"
    )

    # FK to Lookup Project (mirrors prompt_studio_tool)
    lookup_project = models.ForeignKey(
        LookupProject,
        on_delete=models.CASCADE,
        related_name="profiles",
        db_comment="Lookup project this profile belongs to"
    )

    # Required Adapters (same as Prompt Studio)
    vector_store = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        related_name="lookup_profiles_vector_store",
        db_comment="Vector DB adapter for indexing reference data"
    )

    embedding_model = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        related_name="lookup_profiles_embedding",
        db_comment="Embedding adapter for generating vectors"
    )

    llm = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        related_name="lookup_profiles_llm",
        db_comment="LLM adapter for semantic matching"
    )

    x2text = models.ForeignKey(
        AdapterInstance,
        on_delete=models.PROTECT,
        blank=False,
        null=False,
        related_name="lookup_profiles_x2text",
        db_comment="Text extraction adapter for reference data"
    )

    # Vector DB Configuration
    chunk_size = models.IntegerField(
        null=True,
        blank=True,
        default=1000,
        db_comment="Text chunk size for vector indexing"
    )

    chunk_overlap = models.IntegerField(
        null=True,
        blank=True,
        default=200,
        db_comment="Overlap between chunks"
    )

    similarity_top_k = models.IntegerField(
        null=True,
        blank=True,
        default=5,
        db_comment="Number of top similar results to retrieve"
    )

    # Flags
    is_default = models.BooleanField(
        default=False,
        db_comment="Default profile for this lookup project"
    )

    reindex = models.BooleanField(
        default=False,
        db_comment="Flag to trigger reindexing of reference data"
    )

    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="lookup_profiles_created",
        null=True,
        blank=True,
        editable=False
    )

    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="lookup_profiles_modified",
        null=True,
        blank=True,
        editable=False
    )

    class Meta:
        verbose_name = "Lookup Profile Manager"
        verbose_name_plural = "Lookup Profile Managers"
        db_table = "lookup_profile_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["lookup_project", "profile_name"],
                name="unique_lookup_project_profile_name_index"
            )
        ]

    @staticmethod
    def get_default_profile(project: LookupProject) -> "LookupProfileManager":
        """Get default profile for a lookup project."""
        try:
            return LookupProfileManager.objects.get(
                lookup_project=project,
                is_default=True
            )
        except LookupProfileManager.DoesNotExist:
            raise DefaultProfileError("No default profile found for lookup project")
```

---

## Lookup Index Manager

The IndexManager tracks which reference data versions have been indexed in Vector DB:

```python
class LookupIndexManager(BaseModel):
    """Tracks indexed reference data in Vector DB - mirrors Prompt Studio's IndexManager."""

    index_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # FK to Data Source
    data_source = models.ForeignKey(
        LookupDataSource,
        on_delete=models.CASCADE,
        related_name="index_managers",
        db_comment="Reference data source that was indexed"
    )

    # FK to Profile (determines which adapters were used)
    profile = models.ForeignKey(
        LookupProfileManager,
        on_delete=models.CASCADE,
        related_name="index_managers",
        db_comment="Profile used for indexing (contains adapter config)"
    )

    # Vector DB index IDs
    vector_db_index_id = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        db_comment="Index ID in the vector database"
    )

    # Track indexing history
    index_ids_history = models.JSONField(
        default=list,
        db_comment="Historical index IDs for cleanup"
    )

    # Indexing status
    indexing_status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ],
        default='pending',
        db_comment="Status of indexing operation"
    )

    # Metadata
    chunk_count = models.IntegerField(
        null=True,
        blank=True,
        db_comment="Number of chunks created during indexing"
    )

    indexed_at = models.DateTimeField(
        auto_now_add=True,
        db_comment="Timestamp when indexing completed"
    )

    class Meta:
        verbose_name = "Lookup Index Manager"
        verbose_name_plural = "Lookup Index Managers"
        db_table = "lookup_index_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["data_source", "profile"],
                name="unique_data_source_profile_index"
            )
        ]
```

---

## System Workflow

### 1. Profile Creation Workflow

```
User Action: Create New Profile
    ↓
Frontend: Profile Creation Modal
    - Profile Name: "High Accuracy Profile"
    - X2Text Adapter: [Dropdown] → Select LLMWhisperer V2
    - Embedding Adapter: [Dropdown] → Select OpenAI Ada-002
    - Vector DB Adapter: [Dropdown] → Select Qdrant
    - LLM Adapter: [Dropdown] → Select GPT-4
    - Chunk Size: 1000
    - Similarity Top K: 5
    - [x] Set as Default
    ↓
API: POST /api/v1/unstract/{org_id}/lookup/profile-manager/
    {
        "profile_name": "High Accuracy Profile",
        "lookup_project": "project-uuid",
        "x2text": "adapter-instance-uuid-1",
        "embedding_model": "adapter-instance-uuid-2",
        "vector_store": "adapter-instance-uuid-3",
        "llm": "adapter-instance-uuid-4",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "similarity_top_k": 5,
        "is_default": true
    }
    ↓
Backend: Create LookupProfileManager instance
    ↓
Response: Profile created successfully
```

### 2. Reference Data Indexing Workflow

```
User Action: Upload Reference Data File
    ↓
Frontend: Reference Data Tab
    - Upload vendors.csv
    ↓
API: POST /api/v1/unstract/{org_id}/lookup/data-source/
    - Creates LookupDataSource with extraction_status='pending'
    ↓
Backend: Celery Task - Extract and Index
    ↓
Step 1: Get Default Profile
    profile = LookupProfileManager.get_default_profile(project)
    ↓
Step 2: Extract Text using Profile's X2Text Adapter
    x2text = X2Text(
        tool=util,
        adapter_instance_id=profile.x2text.id
    )
    extracted_text = x2text.process(file_content)
    ↓
Step 3: Store Extracted Text in Object Storage
    storage.upload(
        path=f"lookup/{project_id}/{filename}.txt",
        content=extracted_text
    )
    ↓
Step 4: Chunk Text
    chunks = create_chunks(
        text=extracted_text,
        chunk_size=profile.chunk_size,
        overlap=profile.chunk_overlap
    )
    ↓
Step 5: Generate Embeddings using Profile's Embedding Adapter
    embedding = Embedding(
        tool=util,
        adapter_instance_id=profile.embedding_model.id
    )
    vectors = [embedding.embed(chunk) for chunk in chunks]
    ↓
Step 6: Store in Vector DB using Profile's Vector DB Adapter
    vector_db = VectorDB(
        tool=util,
        adapter_instance_id=profile.vector_store.id
    )
    index_id = vector_db.index(
        documents=chunks,
        embeddings=vectors,
        metadata={...}
    )
    ↓
Step 7: Create Index Manager Entry
    LookupIndexManager.objects.create(
        data_source=data_source,
        profile=profile,
        vector_db_index_id=index_id,
        indexing_status='completed',
        chunk_count=len(chunks)
    )
    ↓
Step 8: Update Data Source Status
    data_source.extraction_status = 'completed'
    data_source.save()
```

### 3. Lookup Execution Workflow

```
Prompt Studio Project Executes with Lookup
    ↓
Input Variable: {{vendor_name}} = "Micro soft"  # Typo intentional
    ↓
Backend: Lookup Execution Service
    ↓
Step 1: Get Linked Lookup Project
    lookup_project = get_linked_lookup_project(ps_project)
    ↓
Step 2: Get Default Profile
    profile = LookupProfileManager.get_default_profile(lookup_project)
    ↓
Step 3: Generate Query Embedding using Profile's Embedding Adapter
    embedding = Embedding(
        tool=util,
        adapter_instance_id=profile.embedding_model.id
    )
    query_vector = embedding.embed("Micro soft")
    ↓
Step 4: Search Vector DB using Profile's Vector DB Adapter
    vector_db = VectorDB(
        tool=util,
        adapter_instance_id=profile.vector_store.id
    )
    results = vector_db.search(
        query=query_vector,
        top_k=profile.similarity_top_k,
        filters={...}
    )
    ↓
Step 5: Format Results
    matches = [
        {
            "text": "Microsoft",
            "score": 0.92,
            "metadata": {...}
        },
        {
            "text": "Micro Software Inc",
            "score": 0.78,
            "metadata": {...}
        }
    ]
    ↓
Step 6: LLM Selection (Optional) using Profile's LLM Adapter
    llm = LLM(
        tool=util,
        adapter_instance_id=profile.llm.id
    )
    best_match = llm.select_best_match(
        query="Micro soft",
        candidates=matches
    )
    ↓
Return: "Microsoft" (standardized form)
```

---

## API Endpoints

### Profile Management

```
# List profiles for a project
GET /api/v1/unstract/{org_id}/lookup/profile-manager/?lookup_project={project_id}

# Create new profile
POST /api/v1/unstract/{org_id}/lookup/profile-manager/
{
    "profile_name": "Profile Name",
    "lookup_project": "uuid",
    "x2text": "adapter-instance-uuid",
    "embedding_model": "adapter-instance-uuid",
    "vector_store": "adapter-instance-uuid",
    "llm": "adapter-instance-uuid",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "similarity_top_k": 5,
    "is_default": true
}

# Get profile details
GET /api/v1/unstract/{org_id}/lookup/profile-manager/{profile_id}/

# Update profile
PUT /api/v1/unstract/{org_id}/lookup/profile-manager/{profile_id}/

# Delete profile
DELETE /api/v1/unstract/{org_id}/lookup/profile-manager/{profile_id}/

# Set profile as default
POST /api/v1/unstract/{org_id}/lookup/profile-manager/{profile_id}/set-default/
```

### Index Management

```
# List indexes for a project
GET /api/v1/unstract/{org_id}/lookup/index-manager/?lookup_project={project_id}

# Get index details
GET /api/v1/unstract/{org_id}/lookup/index-manager/{index_id}/

# Trigger reindexing
POST /api/v1/unstract/{org_id}/lookup/index-manager/reindex/
{
    "lookup_project": "uuid",
    "profile": "uuid"  # Optional, uses default if not specified
}
```

---

## Frontend UI Structure

### Project Detail Page - Profile Tab

```jsx
<LookupProjectDetail projectId={projectId}>
  <Tabs>
    <Tab label="Reference Data">
      {/* File uploads */}
    </Tab>

    <Tab label="Templates">
      {/* Lookup templates */}
    </Tab>

    <Tab label="Profiles">  {/* NEW TAB */}
      <ProfileManagementTab projectId={projectId}>

        {/* Profile List */}
        <Table>
          <Row>
            <Column>Profile Name</Column>
            <Column>X2Text</Column>
            <Column>Embedding</Column>
            <Column>Vector DB</Column>
            <Column>LLM</Column>
            <Column>Default</Column>
            <Column>Actions</Column>
          </Row>
          {profiles.map(profile => (
            <Row key={profile.id}>
              <Cell>{profile.profile_name}</Cell>
              <Cell>{profile.x2text.adapter_name}</Cell>
              <Cell>{profile.embedding_model.adapter_name}</Cell>
              <Cell>{profile.vector_store.adapter_name}</Cell>
              <Cell>{profile.llm.adapter_name}</Cell>
              <Cell>
                {profile.is_default ?
                  <Tag color="green">Default</Tag> :
                  <Button onClick={() => setAsDefault(profile.id)}>
                    Set as Default
                  </Button>
                }
              </Cell>
              <Cell>
                <Button onClick={() => editProfile(profile)}>Edit</Button>
                <Button onClick={() => deleteProfile(profile.id)}>Delete</Button>
              </Cell>
            </Row>
          ))}
        </Table>

        {/* Create Profile Button */}
        <Button onClick={() => setShowCreateModal(true)}>
          Create New Profile
        </Button>

      </ProfileManagementTab>
    </Tab>

    <Tab label="Linked Projects">
      {/* Prompt Studio project links */}
    </Tab>

    <Tab label="Execution History">
      {/* Audit logs */}
    </Tab>

    <Tab label="Debug">
      {/* Test execution */}
    </Tab>
  </Tabs>
</LookupProjectDetail>
```

### Profile Creation/Edit Modal

```jsx
<Modal
  title={isEdit ? "Edit Profile" : "Create New Profile"}
  visible={showModal}
  onCancel={() => setShowModal(false)}
  onOk={handleSubmit}
>
  <Form>
    {/* Profile Name */}
    <FormItem label="Profile Name" required>
      <Input
        value={formData.profile_name}
        onChange={e => setFormData({...formData, profile_name: e.target.value})}
        placeholder="e.g., High Accuracy Profile"
      />
    </FormItem>

    {/* X2Text Adapter Selection */}
    <FormItem label="Text Extraction Adapter" required>
      <Select
        value={formData.x2text}
        onChange={value => setFormData({...formData, x2text: value})}
        showSearch
        filterOption={(input, option) =>
          option.children.toLowerCase().includes(input.toLowerCase())
        }
      >
        {x2textAdapters.map(adapter => (
          <Option key={adapter.id} value={adapter.id}>
            {adapter.adapter_name} ({adapter.adapter_type})
          </Option>
        ))}
      </Select>
    </FormItem>

    {/* Embedding Adapter Selection */}
    <FormItem label="Embedding Adapter" required>
      <Select
        value={formData.embedding_model}
        onChange={value => setFormData({...formData, embedding_model: value})}
        showSearch
      >
        {embeddingAdapters.map(adapter => (
          <Option key={adapter.id} value={adapter.id}>
            {adapter.adapter_name} ({adapter.adapter_type})
          </Option>
        ))}
      </Select>
    </FormItem>

    {/* Vector DB Adapter Selection */}
    <FormItem label="Vector Database Adapter" required>
      <Select
        value={formData.vector_store}
        onChange={value => setFormData({...formData, vector_store: value})}
        showSearch
      >
        {vectorDBAdapters.map(adapter => (
          <Option key={adapter.id} value={adapter.id}>
            {adapter.adapter_name} ({adapter.adapter_type})
          </Option>
        ))}
      </Select>
    </FormItem>

    {/* LLM Adapter Selection */}
    <FormItem label="LLM Adapter" required>
      <Select
        value={formData.llm}
        onChange={value => setFormData({...formData, llm: value})}
        showSearch
      >
        {llmAdapters.map(adapter => (
          <Option key={adapter.id} value={adapter.id}>
            {adapter.adapter_name} ({adapter.model_name})
          </Option>
        ))}
      </Select>
    </FormItem>

    {/* Configuration Parameters */}
    <Divider>Vector DB Configuration</Divider>

    <FormItem label="Chunk Size" help="Number of characters per text chunk">
      <InputNumber
        value={formData.chunk_size}
        onChange={value => setFormData({...formData, chunk_size: value})}
        min={100}
        max={5000}
        step={100}
      />
    </FormItem>

    <FormItem label="Chunk Overlap" help="Overlap between consecutive chunks">
      <InputNumber
        value={formData.chunk_overlap}
        onChange={value => setFormData({...formData, chunk_overlap: value})}
        min={0}
        max={1000}
        step={50}
      />
    </FormItem>

    <FormItem label="Similarity Top K" help="Number of top results to retrieve">
      <InputNumber
        value={formData.similarity_top_k}
        onChange={value => setFormData({...formData, similarity_top_k: value})}
        min={1}
        max={20}
      />
    </FormItem>

    {/* Default Profile Checkbox */}
    <FormItem>
      <Checkbox
        checked={formData.is_default}
        onChange={e => setFormData({...formData, is_default: e.target.checked})}
      >
        Set as default profile for this project
      </Checkbox>
    </FormItem>
  </Form>
</Modal>
```

---

## Key Design Principles

### 1. **Consistency with Prompt Studio**
- Same model structure (FK to project, unique constraint on name)
- Same adapter fields (x2text, embedding_model, vector_store, llm)
- Same naming conventions (ProfileManager, is_default, reindex)
- Same API patterns (ViewSet, Serializer, permissions)

### 2. **Profile Ownership**
- Profiles belong to projects (not standalone)
- Each project can have multiple profiles
- One profile is marked as default
- Unique profile names within a project

### 3. **Adapter Flexibility**
- All 4 adapter types required for completeness
- Users select from configured adapters via dropdowns
- No hardcoded adapter choices
- Adapters protected from deletion if in use (PROTECT)

### 4. **Separation of Concerns**
- **LookupProfileManager**: Adapter configuration storage
- **LookupIndexManager**: Indexing state tracking
- **LookupDataSource**: Reference data file metadata
- **LookupExecutor**: Runtime execution logic

### 5. **Audit Trail**
- created_by, modified_by for all changes
- Index history tracking
- Timestamped operations
- Status tracking at every stage

---

## Migration from Old Design

### What Changed

**Old Design (V2)**:
- ProfileManager as optional
- Adapters could be null/blank
- Profile embedded in project creation

**New Design (V3)**:
- ProfileManager required for all operations
- All adapters mandatory
- Profile as separate tab with full CRUD
- Matches Prompt Studio exactly

### Migration Steps

1. **Create default profiles** for all existing lookup projects
2. **Link existing data sources** to profiles via IndexManager
3. **Update UI** to add Profile tab
4. **Add adapter dropdowns** matching Templates screen pattern
5. **Test full workflow** with all adapter types

---

## Next Steps

See [lookup_implementation_plan_v3.md](lookup_implementation_plan_v3.md) for detailed implementation phases.

---

**END OF ARCHITECTURE DOCUMENT**
