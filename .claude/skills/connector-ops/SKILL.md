---
name: connector-ops
description: >
  Manage Unstract connectors - add, remove, or modify database, filesystem, and queue connectors.
  This skill handles backend code, JSON schemas, tests, logo fetching, and dependency management.
  Use when the user wants to create a new connector, delete an existing one, or modify connector behavior.
---

# Connector Operations Skill

Manage Unstract connectors with full lifecycle support: add, remove, and modify operations for database, filesystem, and queue connector types.

## When to Use This Skill

- User requests adding a new connector (e.g., "add a Redis connector", "create MongoDB database connector")
- User requests removing a connector (e.g., "remove the Oracle connector", "delete Box filesystem")
- User requests modifying a connector (e.g., "add SSL support to MySQL", "update BigQuery schema")

## Architecture Overview

Connectors live in `/unstract/connectors/src/unstract/connectors/` with three categories:

| Type | Base Class | Directory | Mode |
|------|------------|-----------|------|
| Database | `UnstractDB` | `databases/` | `ConnectorMode.DATABASE` |
| Filesystem | `UnstractFileSystem` | `filesystems/` | `ConnectorMode.FILE_SYSTEM` |
| Queue | `UnstractQueue` | `queues/` | `ConnectorMode.MANUAL_REVIEW` |

### Connector Structure

Each connector follows this structure:
```
connector_name/
├── __init__.py          # Metadata dict with is_active flag
├── connector_name.py    # Main connector class
├── constants.py         # Optional constants
└── static/
    ├── json_schema.json # Configuration UI schema
    └── settings.yaml    # Optional settings
```

### Key Files

| File | Purpose |
|------|---------|
| `base.py` | Root `UnstractConnector` abstract class |
| `connectorkit.py` | Singleton registry for all connectors |
| `databases/unstract_db.py` | Database connector base class |
| `filesystems/unstract_file_system.py` | Filesystem connector base class |
| `queues/unstract_queue.py` | Queue connector base class |
| `databases/register.py` | Auto-discovery for database connectors |
| `filesystems/register.py` | Auto-discovery for filesystem connectors |

---

## Operation: ADD Connector

### Step 1: Gather Requirements

Ask the user for:
1. **Connector name** (e.g., "Redis", "MongoDB", "Wasabi")
2. **Connector type** (database, filesystem, or queue)
3. **Brief description** of use case

### Step 2: Research the Service

Use web search to discover:
1. **Official Python library** for the service
2. **All supported authentication modes** (API key, OAuth, connection string, certificates, etc.)
3. **Required connection parameters** for each auth mode
4. **Official logo/icon** source

Document findings before proceeding.

### Step 3: Generate Connector ID

Create a unique connector ID using this pattern:
```python
f"{short_name}|{uuid4()}"
# Example: "redis|a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### Step 4: Create Directory Structure

```bash
# For database connector
mkdir -p unstract/connectors/src/unstract/connectors/databases/{connector_name}/static

# For filesystem connector
mkdir -p unstract/connectors/src/unstract/connectors/filesystems/{connector_name}/static

# For queue connector
mkdir -p unstract/connectors/src/unstract/connectors/queues/{connector_name}/static
```

### Step 5: Create Connector Files

#### 5a. Create `__init__.py`

```python
from .{connector_name} import {ClassName}

metadata = {
    "name": {ClassName}.__name__,
    "version": "1.0.0",
    "connector": {ClassName},
    "description": "{Description of the connector}",
    "is_active": True,
}
```

#### 5b. Create Main Connector Class

Use the appropriate template from `assets/templates/`:
- `database_template.py` for database connectors
- `filesystem_template.py` for filesystem connectors
- `queue_template.py` for queue connectors

Read the template and adapt it for the specific service. Key methods to implement:

**For Database Connectors:**
- `get_engine()` → Return database connection
- `sql_to_db_mapping()` → Map Python types to DB types
- `execute()` → Execute queries (inherited, may override)

**For Filesystem Connectors:**
- `get_fsspec_fs()` → Return fsspec filesystem instance
- `test_credentials()` → Verify connection works
- `extract_metadata_file_hash()` → Extract file hash from metadata
- `is_dir_by_metadata()` → Check if path is directory

**For Queue Connectors:**
- `get_engine()` → Return queue connection
- `enqueue()` → Add message to queue
- `dequeue()` → Get message from queue
- `peek()` → View next message without removing

#### 5c. Create JSON Schema

Generate `static/json_schema.json` based on researched auth modes:

```json
{
  "title": "{Connector Display Name}",
  "type": "object",
  "allOf": [
    {
      "required": ["connectorName"],
      "properties": {
        "connectorName": {
          "type": "string",
          "title": "Name of the connector"
        }
      }
    },
    {
      "oneOf": [
        // Add each auth mode as a separate option
      ]
    }
  ]
}
```

Use `"format": "password"` for sensitive fields.

### Step 6: Fetch Logo

Execute the logo fetch script:
```bash
python .claude/skills/connector-ops/scripts/fetch_logo.py "{service_name}" "{output_path}"
```

The script tries these sources in order:
1. **SimpleIcons** (simpleicons.org)
2. **Devicon** (devicon.dev)
3. **Logo.dev API**
4. **Web search** for official logo
5. **Skip** if not found (log warning)

Place logo at: `/frontend/public/icons/connector-icons/{ConnectorName}.png`

### Step 7: Add Dependencies

Research required Python packages and add to `pyproject.toml`:

```bash
# Read current dependencies
cat unstract/connectors/pyproject.toml

# Add new dependency in the [project.dependencies] section
# Follow existing version pinning patterns (e.g., ~=, ==, >=)
```

### Step 8: Create Tests

Generate both mock-based and integration tests in `unstract/connectors/tests/`:

#### Mock-based Test (always runnable):
```python
import unittest
from unittest.mock import patch, Mock

class Test{ClassName}(unittest.TestCase):
    def setUp(self):
        self.config = {
            # Test configuration
        }

    @patch("{module_path}.{connection_method}")
    def test_connection_params(self, mock_connect):
        mock_connect.return_value = Mock()
        connector = {ClassName}(self.config)
        # Assertions
```

#### Integration Test (requires real service):
```python
import os
import unittest

class Test{ClassName}Integration(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("{CONNECTOR}_HOST"),
        "Integration test requires {CONNECTOR}_* environment variables"
    )
    def test_real_connection(self):
        config = {
            "host": os.getenv("{CONNECTOR}_HOST"),
            # ... other env vars
        }
        connector = {ClassName}(config)
        self.assertTrue(connector.test_credentials())
```

### Step 9: Verify

Run verification in order:

```bash
# 1. Syntax/type check
cd unstract/connectors && python -m py_compile src/unstract/connectors/{type}/{name}/{name}.py

# 2. Run mock tests
cd unstract/connectors && python -m pytest tests/{type}/test_{name}.py -v

# 3. Run full connector test suite
cd unstract/connectors && python -m pytest tests/ -v --ignore=tests/{type}/test_{name}_integration.py
```

### Step 10: Report to User

Provide summary:
```
## Connector Added: {Name}

**Files created:**
- `src/unstract/connectors/{type}/{name}/__init__.py`
- `src/unstract/connectors/{type}/{name}/{name}.py`
- `src/unstract/connectors/{type}/{name}/static/json_schema.json`
- `tests/{type}/test_{name}.py`
- `tests/{type}/test_{name}_integration.py`
- `frontend/public/icons/connector-icons/{Name}.png`

**Dependencies added:**
- `{package}~={version}`

**Verification:**
- Syntax check: PASSED
- Mock tests: PASSED (X tests)
- Test suite: PASSED

**To run integration tests:**
```bash
export {CONNECTOR}_HOST=your_host
export {CONNECTOR}_USER=your_user
export {CONNECTOR}_PASSWORD=your_password
cd unstract/connectors && python -m pytest tests/{type}/test_{name}_integration.py -v
```
```

---

## Operation: REMOVE Connector

### Step 1: Identify Connector

Locate the connector by name or ID:
```bash
# Search for connector
grep -r "class {Name}" unstract/connectors/src/
```

### Step 2: Check Dependencies

Search for usages across the codebase:
```bash
grep -r "{connector_id}" --include="*.py" .
grep -r "from.*{connector_name}" --include="*.py" .
```

Warn user if connector is referenced elsewhere.

### Step 3: Remove Files

```bash
# Remove connector directory
rm -rf unstract/connectors/src/unstract/connectors/{type}/{name}/

# Remove tests
rm -f unstract/connectors/tests/{type}/test_{name}*.py

# Remove icon
rm -f frontend/public/icons/connector-icons/{Name}.png
```

### Step 4: Clean Dependencies (Optional)

If the removed connector was the only user of a dependency, offer to remove it from `pyproject.toml`.

### Step 5: Verify

```bash
# Ensure no import errors
cd unstract/connectors && python -c "from unstract.connectors.connectorkit import Connectorkit; Connectorkit()"

# Run test suite
cd unstract/connectors && python -m pytest tests/ -v
```

### Step 6: Report to User

```
## Connector Removed: {Name}

**Files deleted:**
- `src/unstract/connectors/{type}/{name}/` (directory)
- `tests/{type}/test_{name}.py`
- `tests/{type}/test_{name}_integration.py`
- `frontend/public/icons/connector-icons/{Name}.png`

**Verification:**
- Import check: PASSED
- Test suite: PASSED
```

---

## Operation: MODIFY Connector

### Step 1: Understand the Change

Ask user what modification is needed:
- Add new configuration field?
- Add new authentication mode?
- Fix a bug?
- Update dependency version?
- Change behavior?

### Step 2: Locate Files

```bash
# Find connector files
find unstract/connectors -name "*{connector_name}*" -type f
```

### Step 3: Make Changes

Based on modification type:

**Adding configuration field:**
1. Update `static/json_schema.json` with new field
2. Update connector class `__init__` to read new field
3. Update usage of field in connector methods
4. Update tests to cover new field

**Adding authentication mode:**
1. Research new auth mode parameters
2. Add new `oneOf` option in JSON schema
3. Update connector class to handle new auth
4. Add tests for new auth mode

**Bug fix:**
1. Identify root cause
2. Implement fix
3. Add regression test

**Dependency update:**
1. Update version in `pyproject.toml`
2. Check for breaking changes
3. Update connector code if needed
4. Run tests to verify

### Step 4: Update Tests

Ensure tests cover the modification:
- Add new test cases for new functionality
- Update existing tests if behavior changed
- Run full test suite

### Step 5: Verify

```bash
# Type check modified files
cd unstract/connectors && python -m py_compile src/unstract/connectors/{type}/{name}/{name}.py

# Run connector tests
cd unstract/connectors && python -m pytest tests/{type}/test_{name}*.py -v

# Run full suite
cd unstract/connectors && python -m pytest tests/ -v
```

### Step 6: Report to User

```
## Connector Modified: {Name}

**Changes:**
- {Description of each change}

**Files modified:**
- {List of modified files}

**Tests:**
- Added: {count} new test(s)
- Modified: {count} existing test(s)

**Verification:**
- Syntax check: PASSED
- Connector tests: PASSED
- Full suite: PASSED
```

---

## Reference Materials

Consult these files for detailed patterns:
- `references/connector_patterns.md` - Common patterns and anti-patterns
- `references/json_schema_examples.md` - JSON schema examples for all auth types
- `references/test_patterns.md` - Test patterns and fixtures

## Asset Templates

Use these templates as starting points:
- `assets/templates/database_template.py`
- `assets/templates/filesystem_template.py`
- `assets/templates/queue_template.py`
- `assets/templates/init_template.py`
- `assets/templates/json_schema_template.json`
- `assets/templates/test_mock_template.py`
- `assets/templates/test_integration_template.py`

---

## Important Notes

1. **Fork Safety**: For connectors using Google APIs or gRPC, implement lazy loading to prevent SIGSEGV in Celery workers. See Google Drive connector for pattern.

2. **UUID Consistency**: Once a connector ID is assigned, never change it. Existing installations may reference it.

3. **Schema Backwards Compatibility**: When modifying schemas, ensure existing configurations remain valid.

4. **Icon Naming**: Use PascalCase with spaces URL-encoded (e.g., `Google%20Drive.png`).

5. **Test Isolation**: Mock tests should never require external services. Use `@unittest.skipUnless` for integration tests.
