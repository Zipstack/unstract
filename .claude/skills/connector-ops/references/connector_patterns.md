# Connector Patterns Reference

Common patterns and anti-patterns for Unstract connector development.

## Pattern: Fork-Safe Initialization

**Problem**: Connectors using gRPC (Google APIs, etc.) crash with SIGSEGV when Celery forks workers if clients are initialized before fork.

**Solution**: Lazy initialization with thread locks.

```python
class GoogleDriveFS(UnstractFileSystem):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("GoogleDrive")
        # Store settings WITHOUT initializing clients
        self._oauth_settings = {
            "access_token": settings["access_token"],
            "refresh_token": settings["refresh_token"],
        }
        # Lazy initialization
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        """Lazy load client AFTER fork."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:  # Double-check
                    # Import heavy libraries here, not at module level
                    from google.oauth2.credentials import Credentials
                    self._client = self._create_client()
        return self._client
```

**Applies to**: Google Drive, BigQuery, any gRPC-based connector.

---

## Pattern: Connection URL vs Parameters

**Problem**: Users want flexibility - some prefer connection strings, others prefer individual parameters.

**Solution**: Use `oneOf` in JSON schema and handle both in constructor.

```python
def __init__(self, settings: dict[str, Any]):
    self.connection_url = settings.get("connection_url", "")

    if self.connection_url:
        # Parse URL mode
        parsed = urlparse(self.connection_url)
        self.host = parsed.hostname
        self.port = parsed.port
        # ...
    else:
        # Individual params mode
        self.host = settings.get("host", "")
        self.port = settings.get("port", "")
        # ...
```

**Applies to**: All database connectors.

---

## Pattern: SSL/TLS Configuration

**Problem**: Enterprise users require SSL with various configurations.

**Solution**: Support multiple SSL modes.

```python
def __init__(self, settings: dict[str, Any]):
    self.ssl_enabled = settings.get("sslEnabled", False)
    self.ssl_mode = settings.get("sslMode", "require")  # require, verify-ca, verify-full
    self.ssl_cert = settings.get("sslCert", "")
    self.ssl_key = settings.get("sslKey", "")
    self.ssl_ca = settings.get("sslCA", "")

def get_engine(self):
    conn_params = {...}

    if self.ssl_enabled:
        if self.ssl_mode == "require":
            conn_params["ssl"] = True
        elif self.ssl_mode in ("verify-ca", "verify-full"):
            conn_params["ssl"] = {
                "ca": self.ssl_ca,
                "cert": self.ssl_cert,
                "key": self.ssl_key,
            }

    return connect(**conn_params)
```

**JSON Schema pattern**:
```json
{
  "sslEnabled": {
    "type": "boolean",
    "title": "Enable SSL",
    "default": false
  },
  "sslMode": {
    "type": "string",
    "title": "SSL Mode",
    "enum": ["require", "verify-ca", "verify-full"],
    "default": "require"
  }
}
```

---

## Pattern: Credential Testing

**Problem**: Users need feedback on whether their credentials work.

**Solution**: Implement `test_credentials()` with meaningful error messages.

```python
def test_credentials(self) -> bool:
    try:
        conn = self.get_engine()
        # Execute lightweight test query
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        conn.close()
        return True
    except AuthenticationError as e:
        raise ConnectorError(
            f"Authentication failed: {e}",
            treat_as_user_message=True
        )
    except ConnectionRefusedError as e:
        raise ConnectorError(
            f"Connection refused - check host and port: {e}",
            treat_as_user_message=True
        )
    except Exception as e:
        raise ConnectorError(f"Connection error: {e}")
```

---

## Pattern: Type Mapping

**Problem**: Different databases have different type systems.

**Solution**: Implement `sql_to_db_mapping()` comprehensively.

```python
def sql_to_db_mapping(self, value: Any, column_name: str | None = None) -> str:
    """Map Python types to database types."""
    if value is None:
        return "TEXT"  # Default for NULL

    if isinstance(value, bool):
        return "BOOLEAN"
    elif isinstance(value, int):
        return "INTEGER"
    elif isinstance(value, float):
        return "DOUBLE PRECISION"
    elif isinstance(value, dict):
        return "JSONB"  # PostgreSQL-specific
    elif isinstance(value, list):
        return "JSONB"
    elif isinstance(value, datetime):
        return "TIMESTAMP"
    elif isinstance(value, date):
        return "DATE"
    elif isinstance(value, bytes):
        return "BYTEA"
    else:
        return "TEXT"
```

---

## Pattern: Fsspec Integration

**Problem**: Filesystem connectors need consistent interface for file operations.

**Solution**: Use fsspec abstraction.

```python
from fsspec import AbstractFileSystem

class MyStorageFS(UnstractFileSystem):
    def get_fsspec_fs(self) -> AbstractFileSystem:
        from myfs import MyFileSystem
        return MyFileSystem(
            key=self.access_key,
            secret=self.secret_key,
            endpoint_url=self.endpoint,
        )

    def extract_metadata_file_hash(self, metadata: dict[str, Any]) -> str | None:
        """Extract unique file identifier from fsspec metadata."""
        # Different storage systems use different keys
        return metadata.get("ETag") or metadata.get("md5") or metadata.get("contentHash")

    def is_dir_by_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if path is directory from metadata."""
        return metadata.get("type") == "directory" or metadata.get("StorageClass") == "DIRECTORY"
```

---

## Anti-Pattern: Module-Level Heavy Imports

**Bad**:
```python
# At module level - imported when module loads
from google.cloud import bigquery
from google.oauth2 import service_account

class BigQueryDB(UnstractDB):
    ...
```

**Good**:
```python
# No heavy imports at module level

class BigQueryDB(UnstractDB):
    def get_engine(self):
        # Import when needed
        from google.cloud import bigquery
        from google.oauth2 import service_account
        ...
```

**Why**: Heavy imports at module level cause:
- Slow connector discovery
- Memory usage for unused connectors
- Fork safety issues with gRPC

---

## Anti-Pattern: Hardcoded Credentials

**Bad**:
```python
def __init__(self, settings: dict[str, Any]):
    self.password = settings.get("password", "default_password")  # Never!
```

**Good**:
```python
def __init__(self, settings: dict[str, Any]):
    self.password = settings.get("password", "")
    if not self.password:
        raise ConnectorError("Password is required")
```

---

## Anti-Pattern: Changing Connector ID

**Bad**:
```python
# Version 1.0
@staticmethod
def get_id() -> str:
    return "postgres|abc123"

# Version 2.0 - DON'T DO THIS
@staticmethod
def get_id() -> str:
    return "postgresql|xyz789"  # Changed ID breaks existing configs!
```

**Good**: Connector IDs are immutable once deployed.

---

## Pattern: Keepalive Configuration

**Problem**: Long-running queries timeout due to connection drops.

**Solution**: Configure TCP keepalive.

```python
def get_engine(self):
    conn_params = {
        # TCP keepalive settings
        "keepalives": 1,
        "keepalives_idle": 30,      # Seconds before sending keepalive
        "keepalives_interval": 10,  # Seconds between keepalives
        "keepalives_count": 5,      # Failed keepalives before disconnect
        "connect_timeout": 30,
        # ...
    }
    return psycopg2.connect(**conn_params)
```

---

## Pattern: Query Execution with Cursor Management

**Problem**: Resource leaks from unclosed cursors.

**Solution**: Use context managers.

```python
def execute(self, query: str) -> list[tuple]:
    """Execute query with proper resource management."""
    engine = self.get_engine()
    try:
        with engine.cursor() as cursor:
            cursor.execute(query)
            if cursor.description:  # SELECT query
                return cursor.fetchall()
            else:  # INSERT/UPDATE/DELETE
                engine.commit()
                return []
    finally:
        engine.close()
```

---

## Pattern: OAuth Token Refresh

**Problem**: OAuth tokens expire and need refreshing.

**Solution**: Handle token refresh transparently.

```python
def _refresh_token_if_needed(self) -> str:
    """Refresh OAuth token if expired."""
    if self._token_expiry and datetime.now() >= self._token_expiry:
        from google.auth.transport.requests import Request

        credentials = Credentials(
            token=self._access_token,
            refresh_token=self._refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        credentials.refresh(Request())

        self._access_token = credentials.token
        self._token_expiry = credentials.expiry

    return self._access_token
```

---

## Pattern: Batch Operations

**Problem**: Large data transfers are slow with row-by-row operations.

**Solution**: Support batch operations.

```python
def execute_batch(self, query: str, data: list[tuple], batch_size: int = 1000) -> int:
    """Execute query with batched data."""
    engine = self.get_engine()
    total_rows = 0

    try:
        with engine.cursor() as cursor:
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                cursor.executemany(query, batch)
                total_rows += len(batch)
            engine.commit()
    finally:
        engine.close()

    return total_rows
```
