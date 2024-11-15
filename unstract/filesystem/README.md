# Filesystem

The **Filesystem** module manages file storage interactions within the project. It is built on top of the **Unstract SDK**, ensuring consistency and flexibility across different storage backends.


## Key Components
### FileSystem Class
The `FileSystem` class provides methods to configure, authenticate, and initialize storage mechanisms based on predefined types. It uses mappings and environment variables to customize its behavior dynamically.


### Storage Types
- **Workflow Execution Storage**: Temporary storage for workflow-related files.
- **API Execution Storage**: Temporary storage for API-related files.

### Mappings
- **Storage Mapping**: Defines the storage class for each `FileStorageType`.
- **Credentials Mapping**: Associates credentials (from environment variables) with specific `FileStorageType`.
- **Provider Mapping**: Maps environment-based storage providers to `FileStorageType`.

### Environment Variables
The module relies on environment variables for configuration. Below is a detailed list of required variables:

#### Provider Configuration

`WORKFLOW_EXECUTION_FS_PROVIDER`: The provider for workflow execution storage (default: minio).
`API_STORAGE_FS_PROVIDER`: The provider for API execution storage (default: minio).

#### Credential Configuration

`WORKFLOW_EXECUTION_FS_CREDENTIAL`: JSON string containing credentials for workflow execution storage.
`API_STORAGE_FS_CREDENTIAL`: JSON string containing credentials for API execution storage.

#### Additional Configuration

`LEGACY_STORAGE_PATH` (*optional*): Used specifically with **PermanentFileStorage** for legacy data handling.


### Example Environment File (.env)
```env
# Workflow Execution File Storage
WORKFLOW_EXECUTION_FS_PROVIDER=minio
WORKFLOW_EXECUTION_FS_CREDENTIAL={"access_key": "your-access-key", "secret_key": "your-secret-key"}

# API Execution File Storage
API_STORAGE_FS_PROVIDER=minio
API_STORAGE_FS_CREDENTIAL={"access_key": "api-access-key", "secret_key": "api-secret-key"}

# Legacy Storage Path (Optional)
LEGACY_STORAGE_PATH=/path/to/legacy/storage
```

### How It Works
1. **Storage Class Initialization**: Based on `FileStorageType`, the appropriate storage class is chosen from `STORAGE_MAPPING`.
2. **Credential Injection**: Credentials are fetched from environment variables and injected into the storage class.
3. **Provider Selection**: Providers are dynamically resolved using the `get_provider` method and mapped to the relevant `FileStorageType`.
4. **Storage Instance Creation**: A storage instance is created and returned, ready for use.


## Extending the System
To add a new `FileStorageType`:

1. Update the `FileStorageType` enum with the new type.
2. Add the new type to:
   - `STORAGE_MAPPING`: Map the type to a storage class.
   - `FILE_STORAGE_CREDENTIALS_MAPPING`: Define its credentials.
   - `FILE_STORAGE_PROVIDER_MAPPING`: Specify its provider.

# Error Handling
- If a provider is not found in the `FileStorageProvider` enum, a `ProviderNotFound` exception is raised.
- If no valid credentials or mappings are found, the system raises appropriate exceptions (`ValueError`).
