# Unstract Plugin System

## Plugin Metadata Format

Every plugin must define a `metadata` dictionary in its `__init__.py` file. The plugin manager reads this metadata to discover, validate, and load plugins.

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `name` | `str` | Unique plugin identifier | `"my_plugin"` |
| `version` | `str` | Semantic version string | `"1.0.0"` |

### Optional Fields

| Field | Type | Description | Used In |
|-------|------|-------------|---------|
| `description` | `str` | Human-readable description | All |
| `is_active` | `bool` | Enable/disable flag (default: `True`) | All |
| `disable` | `bool` | Explicit disable flag (checked first) | All |
| `entrypoint_cls` | `class` | Main handler class for the plugin | Flask|
| `exception_cls` | `class` | Custom exception class | Flask |
| `service_class` | `callable` | Service factory (usually lambda) | Django Backend |
| `blueprint` | `Blueprint` | Flask blueprint for routes | Flask only |

---

## Creating a New Plugin

### 1. Define Plugin Metadata

**File:** `<service>/plugins/my_plugin/__init__.py`

```python
"""My custom plugin."""

from .service import MyService

metadata = {
    # Required
    "name": "my_plugin",
    "version": "1.0.0",

    # Optional
    "description": "Description of what this plugin does",
    "is_active": True,
    "service_class": lambda: MyService(),
}
```

### 2. Use the Plugin

**Django:**
```python
from backend.plugins import get_plugin

plugin = get_plugin("my_plugin")
result = plugin.some_method()
```

**Flask:**
```python
from unstract.core.flask import plugin_loader

# In create_app()
plugin_manager = plugin_loader(app, plugin_dirs=["service/plugins"])

# In controller
plugin = plugin_manager.get_plugin("my_plugin")
handler = plugin["entrypoint_cls"]()
result = handler.process()
```

---

## Plugin Loading Process

1. **Scans** the configured plugins directory
2. **Skips** items starting with `__` (like `__pycache__`)
3. **Imports** the plugin module (supports `.so` compiled extensions)
4. **Validates** that `metadata` dictionary exists
5. **Checks** if disabled via `metadata.get("disable", False)` or `not metadata.get("is_active", True)`
6. **Registers** plugin with all metadata fields
7. **Calls** registration callback if provided (e.g., for Flask blueprint registration)

## Using Shared Libraries in Plugins

This directory (`unstract.core.plugins`) can contain shared library code that can be used by plugins across all Unstract services (backend, platform-service, prompt-service, workers).

### Import Pattern

Plugins can import shared code as subpackages from `unstract.core.plugins`:

```python
# In your plugin code (e.g., backend/plugins/my_plugin/service.py)
from unstract.core.plugins.xxx import yyy
```

### Directory Structure

```
unstract/core/src/unstract/core/plugins/
├── README.md                    # This file
├── __init__.py                  # Package initialization
├── plugin_manager.py            # Core plugin discovery and loading
```

### When to Add Shared Code Here

Add code to `unstract.core.plugins` when:

- ✅ Multiple plugins need the same functionality
- ✅ The code is framework-agnostic (works in Django, Flask, Workers)
- ✅ You want to avoid code duplication across services

Keep code in service-specific plugins when:

- ❌ Logic is specific to one service only
- ❌ Code depends on service-specific frameworks (Django ORM, Flask blueprints)
- ❌ Business logic is unique to that plugin

---
