# Agent-KV OSS Half — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the OSS half of the Agent-KV product: public async extraction API (`/agent-kv/`), key management, job model, executor dispatch glue, callbacks, internal APIs, sweeps, webhook delivery, and the shared schema-compiler package.

**Architecture:** A new Django app `backend/agent_kv/` (modeled on `global_api_deployment_key/`) exposes the public API and owns auth in-view; jobs dispatch to the (cloud-plugin) `agentic_kv` executor via `dispatch_with_callback`; success/error callbacks run on the callback worker and finalize jobs through internal APIs. The `keys.json` compiler is a standalone package `unstract/agent-kv-schema` so the cloud engine imports the same compiler the API validates with.

**Tech Stack:** Django + DRF (backend), Celery/PG-queue executor dispatch (`pg_queue.executor_rpc`), `unstract.filesystem` object storage, pdfplumber (page counting), pytest with the repo's no-DB mock-collaborator test style.

**Spec:** `docs/superpowers/specs/2026-08-28-agent-kv-api-design.md` — the plan argues from the spec; executors read both. Spec section references (§) below are to that file.

## Global Constraints

- Locked decisions D1–D13 (spec §2) are not re-litigated during implementation.
- Engine code (LLM calls, OCR, QA/challenger) is NOT in scope — cloud repo. Only the schema compiler is ported (spec §5.1).
- Every public endpoint owns auth in-view (the prefix bypasses middleware). Every endpoint must have a 401-without-key test (spec §6.1, §6.8).
- Job lookups always filter by the key's organization; unknown and forbidden both return 404 (spec §6.1).
- Terminal states (COMPLETED/FAILED/CANCELLED) are write-guarded: no later write may overwrite them (spec §5.4).
- Dispatch is `get_executor_dispatcher().dispatch_with_callback(...)`; single UUID `task_id`; enqueue failure terminalizes the job in the view (spec §5.3).
- No document bytes through the broker — object-store refs only (spec §6.4).
- No document content or extracted values in log statements (spec §6.4).
- New backend settings use env vars with defaults, named `AGENT_KV_*`.
- Follow existing test style: `backend/global_api_deployment_key/tests/test_global_key_auth.py` (no test DB; unsaved instances; patched managers; `DJANGO_SETTINGS_MODULE=backend.settings.test`).
- Commit after every task (steps include the commit).
- Python ≥ 3.12 in `unstract/agent-kv-schema` (matches source project).

---

### Task 1: `unstract/agent-kv-schema` package (compiler port + caps)

**Files:**
- Create: `unstract/agent-kv-schema/pyproject.toml`
- Create: `unstract/agent-kv-schema/src/unstract/agent_kv_schema/__init__.py`
- Create: `unstract/agent-kv-schema/src/unstract/agent_kv_schema/dataclasses.py` (ported)
- Create: `unstract/agent-kv-schema/src/unstract/agent_kv_schema/kv_schema.py` (ported)
- Create: `unstract/agent-kv-schema/src/unstract/agent_kv_schema/constraints.py` (ported)
- Create: `unstract/agent-kv-schema/src/unstract/agent_kv_schema/validators.py` (ported)
- Create: `unstract/agent-kv-schema/src/unstract/agent_kv_schema/compile.py` (new)
- Test: `unstract/agent-kv-schema/tests/test_compile.py`

**Interfaces:**
- Consumes: nothing (leaf package, stdlib-only).
- Produces (used by Tasks 6, 10, and the cloud engine):
  - `compile_schema(spec: dict, caps: SchemaCaps | None = None) -> CompiledSchema` — raises `SchemaError` (subclass of `ValueError`) on any structural or cap violation.
  - `SchemaCaps(max_leaves=200, max_arrays=20, max_columns_per_array=40, max_depth=6, max_regex_len=200, max_aliases=10, max_description_len=500, max_constraints=30)`
  - `CompiledSchema(key_specs: list[KeySpec], array_specs: list[ArraySpec], constraints: list[str])`
  - Re-exports: `KeySpec`, `ArraySpec`, `evaluate_constraints`, `validate_format`.

- [ ] **Step 1: Scaffold the package**

`pyproject.toml`:

```toml
[project]
name = "unstract-agent-kv-schema"
version = "0.1.0"
description = "Agent-KV keys.json schema compiler — single source of truth for API validation and the extraction engine"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/unstract"]
```

Create empty `src/unstract/agent_kv_schema/__init__.py` for now (filled in Step 5) and `tests/__init__.py`.

- [ ] **Step 2: Port the four source modules verbatim**

Copy from `~/Devel/Github/unstract-agentic-table/src/kv/` into `src/unstract/agent_kv_schema/`:

| Source | Destination | Change |
|---|---|---|
| `dataclasses.py` | `dataclasses.py` | Keep ONLY `KeySpec` and `ArraySpec` (delete `KeyResult`, `ArrayResult`, `KVExtractionResult` — those are engine result types, not schema types). |
| `kv_schema.py` | `kv_schema.py` | Imports unchanged (`from .dataclasses import KeySpec, ArraySpec`). |
| `constraints.py` | `constraints.py` | Unchanged. |
| `validators.py` | `validators.py` | Unchanged (`from .dataclasses import KeySpec`). |

Do not "improve" the ported code — parity with the engine is the point.

- [ ] **Step 3: Write the failing tests for the wrapper**

`tests/test_compile.py`:

```python
"""compile_schema: structural validation + caps on top of the ported compiler."""
import pytest

from unstract.agent_kv_schema import (
    CompiledSchema, SchemaCaps, SchemaError, compile_schema,
)

VALID = {
    "quotation_number": {"description": "The quote number", "required": True},
    "customer": {"name": {"description": "Bill-to name"}},
    "line_items": {
        "description": "One row per line",
        "_key": "sku",
        "_array": {
            "sku": {"description": "SKU"},
            "total": {"description": "Line total", "format": "currency"},
        },
    },
    "_constraints": ["count('line_items') >= 1"],
}


def test_valid_schema_compiles():
    out = compile_schema(VALID)
    assert isinstance(out, CompiledSchema)
    assert [s.path for s in out.key_specs] == ["quotation_number", "customer.name"]
    assert out.array_specs[0].path == "line_items"
    assert out.constraints == ["count('line_items') >= 1"]


def test_missing_description_is_schema_error():
    with pytest.raises(SchemaError, match="missing a 'description'"):
        compile_schema({"a": {"format": "string"}})


def test_mixed_node_is_schema_error():
    with pytest.raises(SchemaError, match="mixes object children"):
        compile_schema({"a": {"description": "x", "b": {"description": "y"}}})


def test_leaf_cap_enforced():
    spec = {f"k{i}": {"description": "d"} for i in range(5)}
    with pytest.raises(SchemaError, match="max_leaves"):
        compile_schema(spec, caps=SchemaCaps(max_leaves=4))


def test_depth_cap_enforced():
    spec = {"a": {"b": {"c": {"d": {"description": "deep"}}}}}
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(spec, caps=SchemaCaps(max_depth=3))


def test_regex_length_cap():
    spec = {"a": {"description": "d", "format": "regex:" + "x" * 300}}
    with pytest.raises(SchemaError, match="max_regex_len"):
        compile_schema(spec)


def test_bad_constraint_syntax_rejected():
    spec = {"a": {"description": "d"},
            "_constraints": ["__import__('os').system('true')"]}
    with pytest.raises(SchemaError, match="constraint"):
        compile_schema(spec)


def test_constraint_call_allowlist():
    spec = {"a": {"description": "d"}, "_constraints": ["foo('a.b') > 1"]}
    with pytest.raises(SchemaError, match="constraint"):
        compile_schema(spec)


def test_constraints_cap():
    spec = {"a": {"description": "d"},
            "_constraints": ["a > 0"] * 31}
    with pytest.raises(SchemaError, match="max_constraints"):
        compile_schema(spec)


def test_non_dict_top_level_rejected():
    with pytest.raises(SchemaError):
        compile_schema(["not", "a", "dict"])
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd unstract/agent-kv-schema && uv run --with pytest pytest tests/ -v`
Expected: FAIL — `ImportError: cannot import name 'compile_schema'`

- [ ] **Step 5: Implement `compile.py` and `__init__.py`**

`compile.py`:

```python
"""Cap-enforcing, syntax-validating wrapper over the ported compiler.

This is the single entry point both the API (submit-time validation) and the
cloud engine use. Anything compile_schema accepts, the engine must execute;
anything it rejects never reaches OCR or an LLM.
"""
import ast
from dataclasses import dataclass, field

from . import kv_schema
from .dataclasses import ArraySpec, KeySpec


class SchemaError(ValueError):
    """User-facing schema rejection; message is safe to return in a 400."""


@dataclass(frozen=True)
class SchemaCaps:
    max_leaves: int = 200
    max_arrays: int = 20
    max_columns_per_array: int = 40
    max_depth: int = 6
    max_regex_len: int = 200
    max_aliases: int = 10
    max_description_len: int = 500
    max_constraints: int = 30


@dataclass(frozen=True)
class CompiledSchema:
    key_specs: list[KeySpec] = field(default_factory=list)
    array_specs: list[ArraySpec] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


_ALLOWED_CALLS = {"sum", "count", "min", "max", "avg"}
_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.Call, ast.Name, ast.Attribute, ast.Constant, ast.Load,
)


def _check_constraint_syntax(expr: str) -> None:
    """Static allowlist mirroring constraints._evaluate_one's grammar."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise SchemaError(f"constraint does not parse: {expr!r} ({e.msg})") from e
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise SchemaError(
                f"constraint uses disallowed syntax "
                f"({type(node).__name__}): {expr!r}"
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
                raise SchemaError(f"constraint calls a disallowed function: {expr!r}")
            if node.keywords or len(node.args) != 1 or not isinstance(
                node.args[0], ast.Constant
            ) or not isinstance(node.args[0].value, str):
                raise SchemaError(
                    f"constraint aggregate needs one string literal arg: {expr!r}"
                )


def _max_depth(node: object, depth: int = 0) -> int:
    if not isinstance(node, dict):
        return depth
    if "_array" in node:
        return depth + 1  # array columns are row-local, not nesting
    child = [v for v in node.values() if isinstance(v, dict)]
    if not child:
        return depth + 1
    return max(_max_depth(v, depth + 1) for v in child)


def compile_schema(spec: dict, caps: SchemaCaps | None = None) -> CompiledSchema:
    caps = caps or SchemaCaps()
    if not isinstance(spec, dict):
        raise SchemaError("Top-level key schema must be a JSON object")
    if _max_depth({k: v for k, v in spec.items() if k != "_constraints"}) > caps.max_depth:
        raise SchemaError(f"schema exceeds max_depth={caps.max_depth}")
    try:
        key_specs = kv_schema.compile(spec)
        array_specs = kv_schema.compile_arrays(spec)
    except ValueError as e:
        raise SchemaError(str(e)) from e

    if len(key_specs) > caps.max_leaves:
        raise SchemaError(f"schema exceeds max_leaves={caps.max_leaves}")
    if len(array_specs) > caps.max_arrays:
        raise SchemaError(f"schema exceeds max_arrays={caps.max_arrays}")
    for aspec in array_specs:
        if len(aspec.item_specs) > caps.max_columns_per_array:
            raise SchemaError(
                f"array '{aspec.path}' exceeds "
                f"max_columns_per_array={caps.max_columns_per_array}"
            )
    for kspec in key_specs + [s for a in array_specs for s in a.item_specs]:
        if len(kspec.regex_pattern) > caps.max_regex_len:
            raise SchemaError(f"'{kspec.path}' regex exceeds max_regex_len={caps.max_regex_len}")
        if len(kspec.aliases) > caps.max_aliases:
            raise SchemaError(f"'{kspec.path}' exceeds max_aliases={caps.max_aliases}")
        if len(kspec.effective_description) > caps.max_description_len:
            raise SchemaError(
                f"'{kspec.path}' description exceeds "
                f"max_description_len={caps.max_description_len}"
            )

    constraints = spec.get("_constraints", [])
    if not isinstance(constraints, list) or not all(
        isinstance(c, str) for c in constraints
    ):
        raise SchemaError("_constraints must be a list of strings")
    if len(constraints) > caps.max_constraints:
        raise SchemaError(f"schema exceeds max_constraints={caps.max_constraints}")
    for expr in constraints:
        _check_constraint_syntax(expr)

    return CompiledSchema(key_specs=key_specs, array_specs=array_specs,
                          constraints=list(constraints))
```

`__init__.py`:

```python
from .compile import CompiledSchema, SchemaCaps, SchemaError, compile_schema
from .constraints import evaluate_constraints
from .dataclasses import ArraySpec, KeySpec
from .validators import validate_format

__all__ = [
    "ArraySpec", "CompiledSchema", "KeySpec", "SchemaCaps", "SchemaError",
    "compile_schema", "evaluate_constraints", "validate_format",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd unstract/agent-kv-schema && uv run --with pytest pytest tests/ -v`
Expected: all PASS

- [ ] **Step 7: Register the package in the workspace and as a backend dependency**

Add `"unstract/agent-kv-schema"` to the workspace members list in the root `pyproject.toml` (mirror how `unstract/filesystem` is listed), and add `unstract-agent-kv-schema` to `backend/pyproject.toml` dependencies (mirror the workspace-source pattern used for `unstract-filesystem`). Run `uv sync` at repo root; then `cd backend && uv run python -c "from unstract.agent_kv_schema import compile_schema; print('ok')"`.
Expected: `ok`

- [ ] **Step 8: Commit**

```bash
git add unstract/agent-kv-schema pyproject.toml backend/pyproject.toml uv.lock
git commit -m "feat(agent-kv): shared keys.json schema compiler package with caps"
```

---

### Task 2: `FileStorageType.AGENT_KV` in `unstract/filesystem`

**Files:**
- Modify: `unstract/filesystem/src/unstract/filesystem/file_storage_types.py`
- Modify: `unstract/filesystem/src/unstract/filesystem/file_storage_config.py`
- Test: `unstract/filesystem/tests/test_agent_kv_storage_type.py`

**Interfaces:**
- Produces: `FileStorageType.AGENT_KV` usable as `FileSystem(FileStorageType.AGENT_KV).get_file_storage()`; creds env var `AGENT_KV_FILE_STORAGE_CREDENTIALS`.

- [ ] **Step 1: Write the failing test**

```python
from unstract.filesystem.file_storage_config import (
    FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING, STORAGE_MAPPING,
)
from unstract.filesystem.file_storage_types import FileStorageType


def test_agent_kv_type_exists_and_is_mapped():
    t = FileStorageType.AGENT_KV
    assert t.value == "AGENT_KV"
    assert t in STORAGE_MAPPING
    assert (
        FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING[t]
        == "AGENT_KV_FILE_STORAGE_CREDENTIALS"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd unstract/filesystem && uv run --with pytest pytest tests/test_agent_kv_storage_type.py -v`
Expected: FAIL — `AttributeError: AGENT_KV`

- [ ] **Step 3: Implement**

In `file_storage_types.py` add `AGENT_KV = "AGENT_KV"` to the enum. In `file_storage_config.py` add to both dicts:

```python
FileStorageType.AGENT_KV: StorageType.SHARED_TEMPORARY,
```
```python
FileStorageType.AGENT_KV: "AGENT_KV_FILE_STORAGE_CREDENTIALS",
```

- [ ] **Step 4: Run test to verify it passes** (same command)

- [ ] **Step 5: Commit**

```bash
git add unstract/filesystem
git commit -m "feat(agent-kv): AGENT_KV file storage type with its own creds env"
```

---

### Task 3: `backend/agent_kv` app — models, states, terminal write guard

**Files:**
- Create: `backend/agent_kv/__init__.py`, `backend/agent_kv/apps.py`, `backend/agent_kv/constants.py`, `backend/agent_kv/models.py`, `backend/agent_kv/migrations/__init__.py`
- Modify: `backend/backend/settings/base.py` (INSTALLED_APPS — add `"agent_kv"` next to `"global_api_deployment_key"`; new settings block)
- Test: `backend/agent_kv/tests/test_models.py` (+ `tests/__init__.py`)

**Interfaces:**
- Produces (used by every later backend task):
  - `AgentKVKey(DefaultOrganizationMixin, BaseModel)`: `id`, `name`, `description`, `key` (UUID, unique), `is_active`, `created_by`/`modified_by`; unique `(name, organization)`; db_table `agent_kv_key`.
  - `JobStatus(models.TextChoices)`: `PENDING`, `DISPATCHED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.
  - `AgentKVJob(DefaultOrganizationMixin, BaseModel)` fields per spec §5.4: `id` (UUID4 pk), `api_key` (FK AgentKVKey, SET_NULL), `task_id` (UUID null), `status`, `stage` (Char blank), `stages` (JSON, default dict), `pages_total` (int null), `input_ref`/`result_ref` (Char blank), `usage_summary` (JSON null), `error` (Text blank), `dispatched_at`/`completed_at`/`expires_at` (DateTime null), `tags` (JSON default list), `custom_data` (JSON null), `webhook_url` (URL blank); db_table `agent_kv_job`.
  - `AgentKVJob.TERMINAL = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})`
  - `AgentKVJob.mark_terminal(job_id, organization_id, new_status, *, error="", result_ref="", usage_summary=None) -> bool` — a single guarded `UPDATE ... WHERE status NOT IN TERMINAL`; returns True iff one row changed. **This classmethod is the only way any code path may set a terminal state.**

- [ ] **Step 1: Write the failing tests**

`test_models.py` (no-DB style per Global Constraints; the guard test patches the queryset):

```python
"""Terminal-state write guard: the invariant everything else leans on (spec §5.4)."""
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def test_terminal_set_is_exactly_the_three_states():
    assert AgentKVJob.TERMINAL == frozenset(
        {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    )


@mock.patch.object(AgentKVJob, "objects")
def test_mark_terminal_excludes_terminal_rows_and_reports_success(m_objects):
    m_qs = m_objects.filter.return_value.exclude.return_value
    m_qs.update.return_value = 1
    ok = AgentKVJob.mark_terminal(
        job_id=uuid.uuid4(), organization_id="org1",
        new_status=JobStatus.FAILED, error="boom",
    )
    assert ok is True
    _, exclude_kwargs = m_objects.filter.return_value.exclude.call_args
    assert set(exclude_kwargs["status__in"]) == set(AgentKVJob.TERMINAL)
    update_kwargs = m_qs.update.call_args.kwargs
    assert update_kwargs["status"] == JobStatus.FAILED
    assert update_kwargs["error"] == "boom"
    assert "completed_at" in update_kwargs


@mock.patch.object(AgentKVJob, "objects")
def test_mark_terminal_on_already_terminal_row_is_noop_false(m_objects):
    m_objects.filter.return_value.exclude.return_value.update.return_value = 0
    ok = AgentKVJob.mark_terminal(
        job_id=uuid.uuid4(), organization_id="org1",
        new_status=JobStatus.COMPLETED,
    )
    assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest agent_kv/tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: agent_kv`

- [ ] **Step 3: Implement the app**

`apps.py`:

```python
from django.apps import AppConfig


class AgentKvConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "agent_kv"
```

`models.py` (imports mirror `global_api_deployment_key/models.py`):

```python
import uuid

from account_v2.models import User
from django.db import models
from django.utils import timezone
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import DefaultOrganizationMixin


class AgentKVKey(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=512, blank=True, default="")
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="agent_kv_keys_created",
    )
    modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="+",
    )

    class Meta:
        db_table = "agent_kv_key"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "organization"],
                name="unique_agent_kv_key_name_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization})"


class JobStatus(models.TextChoices):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentKVJob(DefaultOrganizationMixin, BaseModel):
    TERMINAL = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey(
        AgentKVKey, on_delete=models.SET_NULL, null=True, related_name="jobs",
    )
    task_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=JobStatus.choices, default=JobStatus.PENDING,
    )
    stage = models.CharField(max_length=32, blank=True, default="")
    stages = models.JSONField(default=dict, blank=True)
    pages_total = models.IntegerField(null=True, blank=True)
    input_ref = models.CharField(max_length=512, blank=True, default="")
    result_ref = models.CharField(max_length=512, blank=True, default="")
    usage_summary = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    custom_data = models.JSONField(null=True, blank=True)
    webhook_url = models.URLField(max_length=1024, blank=True, default="")

    class Meta:
        db_table = "agent_kv_job"
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    @classmethod
    def mark_terminal(
        cls, job_id, organization_id, new_status, *,
        error="", result_ref="", usage_summary=None,
    ) -> bool:
        """The ONLY way to reach a terminal state (spec §5.4 write guard).

        Guarded UPDATE: at-least-once callbacks, cancel, and the sweep can all
        race; whoever lands first wins and everyone else no-ops.
        """
        fields = {"status": new_status, "completed_at": timezone.now()}
        if error:
            fields["error"] = error
        if result_ref:
            fields["result_ref"] = result_ref
        if usage_summary is not None:
            fields["usage_summary"] = usage_summary
        updated = (
            cls.objects.filter(id=job_id, organization_id=organization_id)
            .exclude(status__in=list(cls.TERMINAL))
            .update(**fields)
        )
        return updated == 1
```

`constants.py`:

```python
STAGE_NAMES = [
    "document_processing", "extraction", "qa", "challenge",
    "normalize", "constraints", "codegen", "code_execution",
]
EXECUTOR_NAME = "agentic_kv"
OPERATION_KV_EXTRACT = "kv_extract"
EXECUTION_SOURCE = "agent_kv_api"
```

In `backend/backend/settings/base.py`: add `"agent_kv"` to INSTALLED_APPS (next to `"global_api_deployment_key"`), and a settings block next to the `API_DEPLOYMENT_*` settings:

```python
AGENT_KV_PATH_PREFIX = os.environ.get("AGENT_KV_PATH_PREFIX", "agent-kv")
AGENT_KV_MAX_FILE_SIZE_MB = int(os.environ.get("AGENT_KV_MAX_FILE_SIZE_MB", 50))
AGENT_KV_MAX_PAGES = int(os.environ.get("AGENT_KV_MAX_PAGES", 100))
AGENT_KV_MAX_CALCULATIONS_BYTES = int(
    os.environ.get("AGENT_KV_MAX_CALCULATIONS_BYTES", 20_000)
)
AGENT_KV_MAX_SCHEMA_BYTES = int(os.environ.get("AGENT_KV_MAX_SCHEMA_BYTES", 262_144))
AGENT_KV_RESULT_TTL_DAYS = int(os.environ.get("AGENT_KV_RESULT_TTL_DAYS", 7))
AGENT_KV_MAX_TIMEOUT_SECONDS = int(os.environ.get("AGENT_KV_MAX_TIMEOUT_SECONDS", 300))
AGENT_KV_CONCURRENT_LIMIT = int(os.environ.get("AGENT_KV_CONCURRENT_LIMIT", 5))
AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE = int(
    os.environ.get("AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE", 60)
)
AGENT_KV_SWEEP_GRACE_SECONDS = int(os.environ.get("AGENT_KV_SWEEP_GRACE_SECONDS", 3600))
```

- [ ] **Step 4: Generate the migration**

Run: `cd backend && uv run python manage.py makemigrations agent_kv`
Expected: one migration creating both tables. Inspect it: both models present, the unique constraint and indexes present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest agent_kv/tests/test_models.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agent_kv backend/backend/settings/base.py
git commit -m "feat(agent-kv): app scaffold, key/job models, terminal write guard"
```

---

### Task 4: Key management API (session-side)

**Files:**
- Create: `backend/agent_kv/serializers.py`, `backend/agent_kv/views.py`, `backend/agent_kv/urls.py`
- Modify: `backend/backend/urls_v2.py` (add `path("agent-kv/", include("agent_kv.urls")),` next to the platform-settings include)
- Test: `backend/agent_kv/tests/test_key_management.py`

**Interfaces:**
- Consumes: `AgentKVKey` (Task 3).
- Produces: tenant-scoped endpoints `keys/` (GET list, POST create), `keys/<uuid:pk>/` (GET, PATCH, DELETE), `keys/<uuid:pk>/rotate/` (POST). Mirrors `global_api_deployment_key` exactly: same viewset shape, same permission classes, same rotate semantics (new `key` UUID, return the updated object).

- [ ] **Step 1: Write the failing tests**

`test_key_management.py` — mock-collaborator style; assert (a) `rotate` assigns a fresh UUID and saves, (b) the write serializer rejects a blank `name`, (c) queryset is org-scoped (the viewset's `get_queryset` filters via the org-aware manager — patch and assert the manager used is `AgentKVKey.objects` with no cross-org args):

```python
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv.models import AgentKVKey  # noqa: E402
from agent_kv.serializers import AgentKVKeyWriteSerializer  # noqa: E402
from agent_kv.views import AgentKVKeyViewSet  # noqa: E402


def test_write_serializer_rejects_blank_name():
    s = AgentKVKeyWriteSerializer(data={"name": "", "description": "x"})
    assert not s.is_valid()
    assert "name" in s.errors


def test_rotate_assigns_fresh_key_and_saves():
    key_obj = AgentKVKey(name="k", key=uuid.uuid4())
    old = key_obj.key
    with mock.patch.object(AgentKVKey, "save") as m_save:
        view = AgentKVKeyViewSet()
        view.get_object = lambda: key_obj
        view.format_kwarg = None
        view.request = mock.Mock()
        resp = view.rotate(view.request, pk=str(key_obj.id))
    assert key_obj.key != old
    assert m_save.called
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest agent_kv/tests/test_key_management.py -v`
Expected: FAIL — `ImportError` (serializers/views modules missing)

- [ ] **Step 3: Implement**

Copy the structure of `backend/global_api_deployment_key/serializers.py` and `views.py`, trimmed to this model (no M2M, no allow-all). Serializers: `AgentKVKeySerializer` (read: id, name, description, key, is_active, created_at) and `AgentKVKeyWriteSerializer` (name required max 128, description optional max 512, is_active). Viewset: `AgentKVKeyViewSet(viewsets.ModelViewSet)` with the same permission classes as `GlobalApiDeploymentKeyViewSet` (copy its `permission_classes` line verbatim), org-scoped `get_queryset` (`AgentKVKey.objects.all()` — the `DefaultOrganizationManagerMixin` scopes it), `perform_create` setting `created_by`, and:

```python
    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        key_obj = self.get_object()
        key_obj.key = uuid.uuid4()
        key_obj.save(update_fields=["key", "modified_at"])
        return Response(AgentKVKeySerializer(key_obj).data)
```

`urls.py`: the four paths mirroring `global_api_deployment_key/urls.py` (list/detail/rotate). Mount in `urls_v2.py`.

- [ ] **Step 4: Run tests to verify they pass** (same command)

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv backend/backend/urls_v2.py
git commit -m "feat(agent-kv): org-scoped key management API with rotate"
```

---

### Task 5: Public mount + bearer-key auth

**Files:**
- Create: `backend/agent_kv/key_validator.py`, `backend/agent_kv/exceptions.py`, `backend/agent_kv/execution_urls.py`, `backend/agent_kv/execution_views.py` (stub views for now)
- Modify: `backend/backend/base_urls.py`, `backend/backend/settings/base.py` (WHITELISTED_PATHS)
- Test: `backend/agent_kv/tests/test_auth.py`

**Interfaces:**
- Consumes: `AgentKVKey` (Task 3), `BaseAPIKeyValidator` (`backend/api_v2/api_key_validator.py`).
- Produces:
  - URL mount: `/{AGENT_KV_PATH_PREFIX}/` → `agent_kv.execution_urls` (middleware-bypassed; views own auth).
  - `@AgentKVKeyValidator.validate_api_key` decorator for execution views; on success sets `kwargs["agent_kv_key"]` (the `AgentKVKey` instance) for the wrapped view.
  - `exceptions.py`: `EngineUnavailable` (501), `RateLimited` (429), `JobNotFound` (404) — DRF `APIException` subclasses.

- [ ] **Step 1: Write the failing tests**

`test_auth.py`:

```python
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from api_v2.exceptions import Forbidden  # noqa: E402
from agent_kv.key_validator import AgentKVKeyValidator  # noqa: E402
from agent_kv.models import AgentKVKey  # noqa: E402


def _request(auth=None):
    r = mock.Mock()
    r.headers = {"Authorization": auth} if auth else {}
    return r


def _wrapped():
    @AgentKVKeyValidator.validate_api_key
    def view(self, request, *args, **kwargs):
        return kwargs["agent_kv_key"]
    return view


def test_missing_key_is_forbidden():
    with pytest.raises(Forbidden):
        _wrapped()(mock.Mock(), _request())


@mock.patch.object(AgentKVKey, "objects")
def test_unknown_key_is_forbidden(m_objects):
    m_objects.get.side_effect = AgentKVKey.DoesNotExist
    with pytest.raises(Forbidden):
        _wrapped()(mock.Mock(), _request(f"Bearer {uuid.uuid4()}"))


@mock.patch.object(AgentKVKey, "objects")
def test_valid_key_injected_into_kwargs(m_objects):
    key_obj = AgentKVKey(name="k", is_active=True)
    m_objects.get.return_value = key_obj
    out = _wrapped()(mock.Mock(), _request(f"Bearer {uuid.uuid4()}"))
    assert out is key_obj


@mock.patch.object(AgentKVKey, "objects")
def test_non_uuid_key_is_forbidden_without_db_hit(m_objects):
    with pytest.raises(Forbidden):
        _wrapped()(mock.Mock(), _request("Bearer not-a-uuid"))
    assert not m_objects.get.called


def test_prefix_is_whitelisted():
    from django.conf import settings
    assert f"/{settings.AGENT_KV_PATH_PREFIX}" in settings.WHITELISTED_PATHS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest agent_kv/tests/test_auth.py -v`
Expected: FAIL — `ImportError: agent_kv.key_validator`

- [ ] **Step 3: Implement**

`key_validator.py`:

```python
import logging
import uuid

from api_v2.api_key_validator import BaseAPIKeyValidator
from api_v2.exceptions import Forbidden

from agent_kv.models import AgentKVKey

logger = logging.getLogger(__name__)


class AgentKVKeyValidator(BaseAPIKeyValidator):
    @staticmethod
    def validate_and_process(self, request, func, api_key, *args, **kwargs):
        try:
            uuid.UUID(api_key)
        except (ValueError, AttributeError):
            raise Forbidden("Invalid api key")
        try:
            key_obj = AgentKVKey.objects.get(key=api_key, is_active=True)
        except AgentKVKey.DoesNotExist:
            raise Forbidden("Invalid api key")
        kwargs["agent_kv_key"] = key_obj
        return func(self, request, *args, **kwargs)
```

`exceptions.py`:

```python
from rest_framework.exceptions import APIException


class EngineUnavailable(APIException):
    status_code = 501
    default_detail = "agent-kv engine not available on this deployment"


class RateLimited(APIException):
    status_code = 429
    default_detail = "Too many requests"


class JobNotFound(APIException):
    status_code = 404
    default_detail = "Job not found"
```

`execution_views.py` — stubs so URLs resolve (real views land in Tasks 8–10):

```python
from rest_framework.views import APIView
from rest_framework.response import Response

from agent_kv.key_validator import AgentKVKeyValidator


class SubmitView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, agent_kv_key=None, **kwargs):
        return Response({"detail": "not implemented"}, status=501)
```

`execution_urls.py`:

```python
from django.urls import path

from agent_kv.execution_views import SubmitView

urlpatterns = [
    path("", SubmitView.as_view(), name="agent_kv_submit"),
]
```

`base_urls.py` — after the pipeline mount:

```python
    # Agent-KV product API (views own auth; prefix is middleware-whitelisted)
    path(f"{settings.AGENT_KV_PATH_PREFIX}/", include("agent_kv.execution_urls")),
```

`settings/base.py` — next to the API-deployment whitelist append (copy its comment style):

```python
# Agent-KV public API: bearer-key auth happens in the views.
WHITELISTED_PATHS.append(f"/{AGENT_KV_PATH_PREFIX}")
```

- [ ] **Step 4: Run tests to verify they pass** (same command)

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv backend/backend/base_urls.py backend/backend/settings/base.py
git commit -m "feat(agent-kv): public mount, bearer-key validator, in-view auth"
```

---

### Task 6: Submit request serializer (all §6.1 caps)

**Files:**
- Create: `backend/agent_kv/execution_serializers.py`
- Test: `backend/agent_kv/tests/test_submit_serializer.py`

**Interfaces:**
- Consumes: `compile_schema`/`SchemaError`/`SchemaCaps` (Task 1); settings (Task 3); `pdfplumber` (via sdk1 dependency).
- Produces: `SubmitSerializer` — DRF serializer. After `.is_valid()`: `validated_data` has `file`, `keys` (dict), `document_class` (str ""), `key_notes` (str ""), `calculations` (str ""), `page_start` (int 1), `page_end` (int|None), `qa` (bool True), `challenge` (bool True), `extraction_mode` ("whole-doc"|"per-page"), `structured_output` (bool False), `timeout` (int 0), `tags` (list), `custom_data` (dict|None), `webhook_url` (str ""); plus attributes `serializer.compiled` (`CompiledSchema`) and `serializer.pages_total` (int|None — None for Excel).

- [ ] **Step 1: Write the failing tests**

`test_submit_serializer.py` (build small in-memory files; a 2-page PDF fixture is generated with pdfplumber's test approach — use `pypdf` if present, else commit a tiny 2-page PDF fixture file `backend/agent_kv/tests/fixtures/two_page.pdf` produced once with any tool; the fixture-file route is the default):

```python
import io
import json
import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from agent_kv.execution_serializers import SubmitSerializer  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
VALID_KEYS = {"total": {"description": "Grand total", "format": "currency"}}


def _pdf_upload(name="doc.pdf"):
    with open(os.path.join(FIXTURES, "two_page.pdf"), "rb") as f:
        return SimpleUploadedFile(name, f.read(), content_type="application/pdf")


def _data(**over):
    d = {"file": _pdf_upload(), "keys": json.dumps(VALID_KEYS)}
    d.update(over)
    return d


def test_valid_submit_compiles_and_counts_pages():
    s = SubmitSerializer(data=_data())
    assert s.is_valid(), s.errors
    assert s.pages_total == 2
    assert [k.path for k in s.compiled.key_specs] == ["total"]
    assert s.validated_data["qa"] is True
    assert s.validated_data["challenge"] is True
    assert s.validated_data["extraction_mode"] == "whole-doc"


def test_disallowed_extension_rejected():
    bad = SimpleUploadedFile("doc.exe", b"MZ", content_type="application/x-dos")
    s = SubmitSerializer(data=_data(file=bad))
    assert not s.is_valid()
    assert "file" in s.errors


def test_oversize_file_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        m.AGENT_KV_MAX_FILE_SIZE_MB = 0
        m.AGENT_KV_MAX_PAGES = 100
        m.AGENT_KV_MAX_SCHEMA_BYTES = 262_144
        m.AGENT_KV_MAX_CALCULATIONS_BYTES = 20_000
        m.AGENT_KV_MAX_TIMEOUT_SECONDS = 300
        s = SubmitSerializer(data=_data())
        assert not s.is_valid()
        assert "file" in s.errors


def test_page_cap_rejected():
    with mock.patch("agent_kv.execution_serializers.settings") as m:
        m.AGENT_KV_MAX_FILE_SIZE_MB = 50
        m.AGENT_KV_MAX_PAGES = 1
        m.AGENT_KV_MAX_SCHEMA_BYTES = 262_144
        m.AGENT_KV_MAX_CALCULATIONS_BYTES = 20_000
        m.AGENT_KV_MAX_TIMEOUT_SECONDS = 300
        s = SubmitSerializer(data=_data())
        assert not s.is_valid()
        assert "pages" in str(s.errors).lower()


def test_bad_schema_is_field_error_not_500():
    s = SubmitSerializer(data=_data(keys=json.dumps({"a": {"format": "string"}})))
    assert not s.is_valid()
    assert "keys" in s.errors


def test_keys_not_json_rejected():
    s = SubmitSerializer(data=_data(keys="{not json"))
    assert not s.is_valid()
    assert "keys" in s.errors


def test_calculations_cap():
    s = SubmitSerializer(data=_data(calculations="x" * 30_000))
    assert not s.is_valid()
    assert "calculations" in s.errors


def test_timeout_bounds():
    s = SubmitSerializer(data=_data(timeout=301))
    assert not s.is_valid()
    s2 = SubmitSerializer(data=_data(timeout=0))
    assert s2.is_valid(), s2.errors


def test_page_range_validation():
    s = SubmitSerializer(data=_data(page_start=5, page_end=2))
    assert not s.is_valid()
```

Also add the fixture: generate `fixtures/two_page.pdf` (any minimal 2-page PDF; `uv run --with pypdf python -c "from pypdf import PdfWriter; w=PdfWriter(); [w.add_blank_page(width=200,height=200) for _ in range(2)]; w.write('backend/agent_kv/tests/fixtures/two_page.pdf')"`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest agent_kv/tests/test_submit_serializer.py -v`
Expected: FAIL — `ImportError: agent_kv.execution_serializers`

- [ ] **Step 3: Implement `execution_serializers.py`**

```python
"""Submit-time validation: every §6.1 cap lives here, before any paid work."""
import json

import pdfplumber
from django.conf import settings
from rest_framework import serializers

from unstract.agent_kv_schema import SchemaError, compile_schema

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tiff"}
PDF_LIKE = {".pdf"}
IMAGE_LIKE = {".png", ".jpg", ".jpeg", ".tiff"}
EXTRACTION_MODES = ("whole-doc", "per-page")


class SubmitSerializer(serializers.Serializer):
    file = serializers.FileField()
    keys = serializers.CharField()  # JSON string or file part read as string
    document_class = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=256
    )
    key_notes = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=10_000
    )
    calculations = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    page_start = serializers.IntegerField(required=False, default=1, min_value=1)
    page_end = serializers.IntegerField(required=False, default=None, allow_null=True, min_value=1)
    qa = serializers.BooleanField(required=False, default=True)
    challenge = serializers.BooleanField(required=False, default=True)
    extraction_mode = serializers.ChoiceField(
        required=False, choices=EXTRACTION_MODES, default="whole-doc"
    )
    structured_output = serializers.BooleanField(required=False, default=False)
    timeout = serializers.IntegerField(required=False, default=0, min_value=0)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, default=list,
        max_length=20,
    )
    custom_data = serializers.JSONField(required=False, default=None, allow_null=True)
    webhook_url = serializers.URLField(
        required=False, allow_blank=True, default="", max_length=1024
    )

    compiled = None
    pages_total = None

    def validate_file(self, f):
        name = (f.name or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'; allowed: {sorted(ALLOWED_EXTENSIONS)}"
            )
        max_bytes = settings.AGENT_KV_MAX_FILE_SIZE_MB * 1024 * 1024
        if f.size > max_bytes:
            raise serializers.ValidationError(
                f"File exceeds {settings.AGENT_KV_MAX_FILE_SIZE_MB}MB limit"
            )
        return f

    def validate_calculations(self, v):
        if len(v.encode("utf-8")) > settings.AGENT_KV_MAX_CALCULATIONS_BYTES:
            raise serializers.ValidationError(
                f"calculations exceeds {settings.AGENT_KV_MAX_CALCULATIONS_BYTES} bytes"
            )
        return v

    def validate_timeout(self, v):
        if v > settings.AGENT_KV_MAX_TIMEOUT_SECONDS:
            raise serializers.ValidationError(
                f"timeout must be 0..{settings.AGENT_KV_MAX_TIMEOUT_SECONDS}"
            )
        return v

    def validate_keys(self, raw):
        # Spec §7.1: `keys` may arrive as an inline JSON string OR a file part.
        # DRF hands a file part to CharField as the UploadedFile object's repr,
        # so the view normalizes: SubmitView reads a file-typed `keys` part into
        # a string BEFORE constructing the serializer (see Task 8 Step 7 note).
        if len(raw.encode("utf-8")) > settings.AGENT_KV_MAX_SCHEMA_BYTES:
            raise serializers.ValidationError("keys schema too large")
        try:
            spec = json.loads(raw)
        except (ValueError, TypeError) as e:
            raise serializers.ValidationError(f"keys is not valid JSON: {e}")
        try:
            self.compiled = compile_schema(spec)
        except SchemaError as e:
            raise serializers.ValidationError(str(e))
        return spec

    def validate(self, data):
        start, end = data.get("page_start", 1), data.get("page_end")
        if end is not None and end < start:
            raise serializers.ValidationError(
                {"page_end": "page_end must be >= page_start"}
            )
        f = data["file"]
        ext = "." + f.name.lower().rsplit(".", 1)[-1]
        if ext in PDF_LIKE:
            try:
                with pdfplumber.open(f) as pdf:
                    self.pages_total = len(pdf.pages)
            except Exception:
                raise serializers.ValidationError({"file": "Unreadable PDF"})
            finally:
                f.seek(0)
            if self.pages_total > settings.AGENT_KV_MAX_PAGES:
                raise serializers.ValidationError(
                    {"file": f"Document has {self.pages_total} pages; "
                             f"max is {settings.AGENT_KV_MAX_PAGES} (§6.1)"}
                )
        elif ext in IMAGE_LIKE:
            self.pages_total = 1
        # Excel: no page concept pre-OCR (spec §6.1); pages_total stays None,
        # size cap already enforced; the engine enforces the post-OCR cap.
        return data
```

- [ ] **Step 4: Run tests to verify they pass** (same command)

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv
git commit -m "feat(agent-kv): submit serializer enforcing every pre-paid-work cap"
```

---

### Task 7: Concurrency limiter + per-key rate limit

**Files:**
- Create: `backend/agent_kv/rate_limiter.py`
- Test: `backend/agent_kv/tests/test_rate_limiter.py`

**Interfaces:**
- Consumes: the Redis client access pattern used by `backend/api_v2/rate_limiter.py` (read it first; reuse its cache/redis handle acquisition line-for-line).
- Produces:
  - `AgentKVConcurrencyLimiter.check_and_acquire(organization_id: str, job_id: str) -> bool` — Redis ZSET `agent_kv:inflight:{org_id}`, limit `settings.AGENT_KV_CONCURRENT_LIMIT`, member TTL 6h. **Fails open** on Redis errors (spec §6.1 accepts this for concurrency; log a warning).
  - `AgentKVConcurrencyLimiter.release(organization_id: str, job_id: str) -> None` — called by the finalize internal view (Task 11) and the sweep (Task 14).
  - `check_key_rate(key_id: str) -> bool` — fixed 60s window counter `agent_kv:rate:{key_id}:{epoch_minute}` with 120s TTL against `settings.AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE`. Fails open with a warning.

- [ ] **Step 1: Write the failing tests** — patch the Redis handle; assert: acquire under limit → True and ZADD called with the job id; at limit → False and no ZADD; release → ZREM; key-rate over limit → False; Redis exception → True (fail-open) for all three.

```python
import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv import rate_limiter as rl  # noqa: E402


@mock.patch.object(rl, "_redis")
def test_acquire_under_limit(m_redis):
    m_redis.return_value.zcard.return_value = 2
    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is True
    assert m_redis.return_value.zadd.called


@mock.patch.object(rl, "_redis")
def test_acquire_at_limit_refused(m_redis):
    m_redis.return_value.zcard.return_value = 5
    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is False
    assert not m_redis.return_value.zadd.called


@mock.patch.object(rl, "_redis")
def test_release_removes_member(m_redis):
    rl.AgentKVConcurrencyLimiter.release("org1", "job1")
    m_redis.return_value.zrem.assert_called_once_with(
        "agent_kv:inflight:org1", "job1"
    )


@mock.patch.object(rl, "_redis")
def test_redis_error_fails_open(m_redis):
    m_redis.return_value.zcard.side_effect = ConnectionError("down")
    assert rl.AgentKVConcurrencyLimiter.check_and_acquire("org1", "job1") is True


@mock.patch.object(rl, "_redis")
def test_key_rate_over_limit(m_redis):
    m_redis.return_value.incr.return_value = 61
    assert rl.check_key_rate("key1") is False


@mock.patch.object(rl, "_redis")
def test_key_rate_under_limit(m_redis):
    m_redis.return_value.incr.return_value = 3
    assert rl.check_key_rate("key1") is True
```

- [ ] **Step 2: Run to verify failure** — `cd backend && uv run pytest agent_kv/tests/test_rate_limiter.py -v` → `ImportError`.

- [ ] **Step 3: Implement `rate_limiter.py`** — `_redis()` returns the same handle `api_v2/rate_limiter.py` uses (copy its acquisition). ZSET semantics: score = epoch seconds; on acquire first `zremrangebyscore` entries older than 6h (self-healing against leaked slots), then `zcard` vs limit, then `zadd`. `check_key_rate` uses `incr` + `expire(nx)` on the minute key. All three wrapped in `try/except Exception: log.warning(...); return True/None` (fail-open).

```python
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_SLOT_TTL_SECONDS = 6 * 3600


def _redis():
    # Same handle acquisition as api_v2.rate_limiter — copy that import/call here.
    from api_v2.rate_limiter import APIDeploymentRateLimiter
    return APIDeploymentRateLimiter._get_redis_client()


class AgentKVConcurrencyLimiter:
    @staticmethod
    def _key(organization_id: str) -> str:
        return f"agent_kv:inflight:{organization_id}"

    @classmethod
    def check_and_acquire(cls, organization_id: str, job_id: str) -> bool:
        try:
            r = _redis()
            now = time.time()
            key = cls._key(organization_id)
            r.zremrangebyscore(key, 0, now - _SLOT_TTL_SECONDS)
            if r.zcard(key) >= settings.AGENT_KV_CONCURRENT_LIMIT:
                return False
            r.zadd(key, {job_id: now})
            r.expire(key, _SLOT_TTL_SECONDS)
            return True
        except Exception:
            logger.warning("agent-kv concurrency limiter failing open", exc_info=True)
            return True

    @classmethod
    def release(cls, organization_id: str, job_id: str) -> None:
        try:
            _redis().zrem(cls._key(organization_id), job_id)
        except Exception:
            logger.warning("agent-kv slot release failed", exc_info=True)


def check_key_rate(key_id: str) -> bool:
    try:
        r = _redis()
        window = int(time.time() // 60)
        key = f"agent_kv:rate:{key_id}:{window}"
        count = r.incr(key)
        r.expire(key, 120)
        return count <= settings.AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE
    except Exception:
        logger.warning("agent-kv key rate limiter failing open", exc_info=True)
        return True
```

If `APIDeploymentRateLimiter` has no `_get_redis_client` helper, extract whatever inline handle it builds into `_redis()` here directly (do NOT modify api_v2).

- [ ] **Step 4: Run tests to verify they pass** (same command)

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv
git commit -m "feat(agent-kv): own-namespace concurrency limiter + per-key rate limit"
```

---

### Task 8: Storage helpers, dispatch glue, and the real Submit view

**Files:**
- Create: `backend/agent_kv/storage.py`, `backend/agent_kv/dispatch.py`
- Modify: `backend/agent_kv/execution_views.py` (replace the stub SubmitView)
- Test: `backend/agent_kv/tests/test_storage.py`, `backend/agent_kv/tests/test_dispatch.py`, `backend/agent_kv/tests/test_submit_view.py`

**Interfaces:**
- Consumes: `SubmitSerializer` (Task 6), limiters (Task 7), `AgentKVJob`/`JobStatus`/constants (Task 3), `EngineUnavailable`/`RateLimited` (Task 5), `FileStorageType.AGENT_KV` (Task 2), `get_plugin` (`backend/plugins/__init__.py:37`), `get_executor_dispatcher` (`backend/pg_queue/executor_rpc.py`), `ExecutionContext` (`unstract.sdk1.execution.context`), platform key via `platform_settings_v2.platform_auth_service.PlatformAuthenticationService.get_active_platform_key` (the `PromptStudioHelper._get_platform_api_key` pattern, `prompt_studio_helper.py:341-354`).
- Produces:
  - `storage.stage_input(org_id: str, job_id: str, uploaded_file) -> str` (returns object-store path `org/{org_id}/agent_kv/{job_id}/input{ext}`); `storage.write_result(org_id, job_id, result: dict) -> str`; `storage.read_result(result_ref: str) -> dict`; `storage.delete_job_files(job: AgentKVJob) -> None`.
  - `dispatch.dispatch_job(job: AgentKVJob, *, schema: dict, options: dict) -> None` — raises `dispatch.DispatchError` on enqueue failure. Side effects on success: `job.task_id`, `status=DISPATCHED`, `dispatched_at` saved.
  - **Cloud executor contract (consumed by the cloud plugin — freeze it):** `ExecutionContext(executor_name="agentic_kv", operation="kv_extract", run_id=str(job.id), execution_source="agent_kv_api", organization_id=org_id, executor_params={...})` where `executor_params` = `{"job_id", "input_ref", "schema" (dict), "options": {"qa", "challenge", "extraction_mode", "structured_output", "page_start", "page_end", "document_class", "key_notes", "calculations"}, "platform_api_key", "max_pages"}`. Callbacks: `signature("agent_kv_complete", kwargs={"callback_kwargs": {"job_id", "org_id"}}, queue="agent_kv_callback")` and the same for `agent_kv_error`.

- [ ] **Step 1: Write the failing storage tests** — patch `unstract.filesystem.FileSystem`; assert `stage_input` writes to `org/{org}/agent_kv/{job}/input.pdf` and returns that path; `write_result` writes JSON to `.../result.json`; `delete_job_files` removes both refs and tolerates missing files.

```python
import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv import storage  # noqa: E402


@mock.patch.object(storage, "FileSystem")
def test_stage_input_path_and_write(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    up = mock.Mock()
    up.name = "invoice.PDF"
    up.chunks.return_value = [b"a", b"b"]
    ref = storage.stage_input("org1", "job1", up)
    assert ref == "org/org1/agent_kv/job1/input.pdf"
    assert fh.write.called


@mock.patch.object(storage, "FileSystem")
def test_write_and_read_result_roundtrip_path(m_fs):
    fh = m_fs.return_value.get_file_storage.return_value
    ref = storage.write_result("org1", "job1", {"success": True})
    assert ref == "org/org1/agent_kv/job1/result.json"
    fh.json_dump.assert_called_once()
```

(Adjust `fh.write`/`fh.json_dump` method names to the real `FileStorage` API — open `unstract/filesystem/.../filesystem.py` and the `FileStorage` class it returns, and use its actual write/read/json methods; the test asserts the path contract, which is the part that must not drift.)

- [ ] **Step 2: Write the failing dispatch tests**

```python
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from agent_kv import dispatch  # noqa: E402
from agent_kv.models import AgentKVJob, JobStatus  # noqa: E402


def _job():
    j = AgentKVJob(id=uuid.uuid4(), input_ref="org/o/agent_kv/j/input.pdf")
    j.organization_id = "org1"
    return j


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
@mock.patch.object(AgentKVJob, "save")
def test_dispatch_success_stamps_job(m_save, m_disp, m_key):
    job = _job()
    dispatch.dispatch_job(job, schema={"a": {"description": "d"}}, options={"qa": True})
    ctx = m_disp.return_value.dispatch_with_callback.call_args.args[0]
    assert ctx.executor_name == "agentic_kv"
    assert ctx.operation == "kv_extract"
    assert ctx.run_id == str(job.id)
    assert ctx.executor_params["platform_api_key"] == "pk"
    kw = m_disp.return_value.dispatch_with_callback.call_args.kwargs
    assert kw["on_success"].task == "agent_kv_complete"
    assert kw["on_error"].task == "agent_kv_error"
    assert kw["task_id"] == str(job.task_id)
    assert job.status == JobStatus.DISPATCHED
    assert job.dispatched_at is not None
    assert m_save.called


@mock.patch.object(dispatch, "_platform_api_key", return_value="pk")
@mock.patch.object(dispatch, "_dispatcher")
def test_enqueue_failure_raises_dispatch_error(m_disp, m_key):
    m_disp.return_value.dispatch_with_callback.side_effect = RuntimeError("broker down")
    with pytest.raises(dispatch.DispatchError):
        dispatch.dispatch_job(_job(), schema={}, options={})
```

- [ ] **Step 3: Write the failing submit-view tests** — patch serializer collaborators; assert: plugin probe falsy → 501 before any staging/dispatch; rate-limit refusal → 429 and no job row; happy path → job created PENDING, staged, dispatched, 202 body has `job_id`/`status`/`status_url`; dispatch raising `DispatchError` → `mark_terminal(FAILED)` called and 500 body carries user-safe error; `timeout=0` returns immediately.

```python
import os
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from rest_framework.test import APIRequestFactory  # noqa: E402
from agent_kv import execution_views as ev  # noqa: E402
from agent_kv.models import AgentKVKey  # noqa: E402


def _post(data=None):
    return APIRequestFactory().post("/agent-kv/", data or {}, format="multipart")


@mock.patch.object(ev, "get_plugin", return_value=None)
@mock.patch.object(AgentKVKey, "objects")
def test_absent_plugin_501s_before_anything(m_keys, m_plugin):
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    req = _post()
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    resp = ev.SubmitView.as_view()(req)
    assert resp.status_code == 501
```

(plus the 429 / happy-path / dispatch-failure / timeout cases in the same style — each patches `ev.get_plugin` truthy, `ev.SubmitSerializer`, `ev.stage_input`, `ev.dispatch_job`, `ev.AgentKVConcurrencyLimiter`, `ev.check_key_rate`, and `AgentKVJob.objects.create` — write all five, following the first's shape.)

- [ ] **Step 4: Run all three test files to verify failure**

Run: `cd backend && uv run pytest agent_kv/tests/test_storage.py agent_kv/tests/test_dispatch.py agent_kv/tests/test_submit_view.py -v`
Expected: ImportErrors / stub 501s where real logic is asserted

- [ ] **Step 5: Implement `storage.py`**

```python
"""Object-store staging/results for agent-kv (spec §5.4, §6.4).

Paths are the contract: org/{org_id}/agent_kv/{job_id}/input{ext} and
.../result.json. No document bytes ever ride the broker.
"""
import json
import logging
import os

from unstract.filesystem import FileStorageType, FileSystem

logger = logging.getLogger(__name__)


def _fs():
    return FileSystem(FileStorageType.AGENT_KV).get_file_storage()


def _base(org_id: str, job_id: str) -> str:
    return f"org/{org_id}/agent_kv/{job_id}"


def stage_input(org_id: str, job_id: str, uploaded_file) -> str:
    ext = os.path.splitext(uploaded_file.name or "")[1].lower() or ".bin"
    ref = f"{_base(org_id, job_id)}/input{ext}"
    fh = _fs()
    data = b"".join(chunk for chunk in uploaded_file.chunks())
    fh.write(path=ref, mode="wb", data=data)
    return ref


def write_result(org_id: str, job_id: str, result: dict) -> str:
    ref = f"{_base(org_id, job_id)}/result.json"
    _fs().json_dump(path=ref, data=result)
    return ref


def read_result(result_ref: str) -> dict:
    raw = _fs().read(path=result_ref, mode="rb")
    return json.loads(raw)


def delete_job_files(job) -> None:
    fh = _fs()
    for ref in (job.input_ref, job.result_ref):
        if not ref:
            continue
        try:
            fh.rm(ref)
        except Exception:
            logger.warning("agent-kv cleanup: could not remove %s", ref)
```

(As in the tests: align `write`/`json_dump`/`read`/`rm` with the actual `FileStorage` API surface before finishing this step.)

- [ ] **Step 6: Implement `dispatch.py`**

```python
"""Executor dispatch glue (spec §5.3). One dispatch per job; UUID task_id."""
import logging
import uuid

from celery import signature
from django.utils import timezone

from unstract.sdk1.execution.context import ExecutionContext

from agent_kv.constants import EXECUTOR_NAME, EXECUTION_SOURCE, OPERATION_KV_EXTRACT
from agent_kv.models import JobStatus

logger = logging.getLogger(__name__)

CALLBACK_QUEUE = "agent_kv_callback"


class DispatchError(Exception):
    """Enqueue failed; the caller terminalizes the job (spec §5.3)."""


def _dispatcher():
    from backend.celery_service import app as celery_app
    from pg_queue.executor_rpc import get_executor_dispatcher
    return get_executor_dispatcher(celery_app=celery_app)


def _platform_api_key(org_id: str) -> str:
    from platform_settings_v2.platform_auth_service import (
        PlatformAuthenticationService,
    )
    platform_key = PlatformAuthenticationService.get_active_platform_key(org_id)
    if not platform_key:
        raise DispatchError(f"No active platform key for org {org_id}")
    return str(platform_key.key)


def dispatch_job(job, *, schema: dict, options: dict) -> None:
    org_id = str(job.organization_id)
    job.task_id = uuid.uuid4()
    context = ExecutionContext(
        executor_name=EXECUTOR_NAME,
        operation=OPERATION_KV_EXTRACT,
        run_id=str(job.id),
        execution_source=EXECUTION_SOURCE,
        organization_id=org_id,
        executor_params={
            "job_id": str(job.id),
            "input_ref": job.input_ref,
            "schema": schema,
            "options": options,
            "platform_api_key": _platform_api_key(org_id),
            "max_pages": job.pages_total,
        },
    )
    cb_kwargs = {"callback_kwargs": {"job_id": str(job.id), "org_id": org_id}}
    try:
        _dispatcher().dispatch_with_callback(
            context,
            on_success=signature(
                "agent_kv_complete", kwargs=cb_kwargs, queue=CALLBACK_QUEUE
            ),
            on_error=signature(
                "agent_kv_error", kwargs=cb_kwargs, queue=CALLBACK_QUEUE
            ),
            task_id=str(job.task_id),
        )
    except Exception as e:
        raise DispatchError(str(e)) from e
    job.status = JobStatus.DISPATCHED
    job.dispatched_at = timezone.now()
    job.save(update_fields=["task_id", "status", "dispatched_at", "modified_at"])
```

(Verify the celery app import path by opening `prompt_studio_helper.py`'s `_get_dispatcher` and copying its exact `celery_app` source.)

- [ ] **Step 7: Implement the real `SubmitView`**

Replace the stub in `execution_views.py`:

```python
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from plugins import get_plugin
from rest_framework.response import Response
from rest_framework.views import APIView

from agent_kv.dispatch import DispatchError, dispatch_job
from agent_kv.exceptions import EngineUnavailable, RateLimited
from agent_kv.execution_serializers import SubmitSerializer
from agent_kv.key_validator import AgentKVKeyValidator
from agent_kv.models import AgentKVJob, JobStatus
from agent_kv.rate_limiter import AgentKVConcurrencyLimiter, check_key_rate
from agent_kv.storage import stage_input

logger = logging.getLogger(__name__)


class SubmitView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, agent_kv_key=None, **kwargs):
        if not get_plugin("agent_kv"):
            raise EngineUnavailable()
        if not check_key_rate(str(agent_kv_key.id)):
            raise RateLimited()

        data = request.data.copy()
        keys_part = data.get("keys")
        if hasattr(keys_part, "read"):  # `keys` uploaded as a file part (§7.1)
            data["keys"] = keys_part.read().decode("utf-8", errors="replace")
        serializer = SubmitSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        org_id = str(agent_kv_key.organization_id)

        job = AgentKVJob(
            api_key=agent_kv_key,
            organization_id=agent_kv_key.organization_id,
            pages_total=serializer.pages_total,
            tags=v["tags"],
            custom_data=v["custom_data"],
            webhook_url=v["webhook_url"],
            expires_at=timezone.now()
            + timedelta(days=settings.AGENT_KV_RESULT_TTL_DAYS),
        )
        if not AgentKVConcurrencyLimiter.check_and_acquire(org_id, str(job.id)):
            raise RateLimited("Concurrent job limit reached")

        job.input_ref = stage_input(org_id, str(job.id), v["file"])
        job.save()

        options = {
            k: v[k]
            for k in ("qa", "challenge", "extraction_mode", "structured_output",
                      "page_start", "page_end", "document_class", "key_notes",
                      "calculations")
        }
        try:
            dispatch_job(job, schema=v["keys"], options=options)
        except DispatchError:
            logger.error("agent-kv dispatch failed for job %s", job.id, exc_info=True)
            AgentKVJob.mark_terminal(
                job.id, job.organization_id, JobStatus.FAILED,
                error="Job could not be dispatched; nothing was billed.",
            )
            AgentKVConcurrencyLimiter.release(org_id, str(job.id))
            return Response(
                {"job_id": str(job.id), "status": JobStatus.FAILED,
                 "error": "Job could not be dispatched; nothing was billed."},
                status=500,
            )

        wait = v["timeout"]
        if wait:
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                job.refresh_from_db()
                if job.status in AgentKVJob.TERMINAL:
                    from agent_kv.execution_views_result import result_payload
                    return Response(result_payload(job), status=200)
                time.sleep(1)

        return Response(
            {
                "job_id": str(job.id),
                "status": job.status,
                "status_url": f"/{settings.AGENT_KV_PATH_PREFIX}/{job.id}",
                "created_at": job.created_at.isoformat(),
            },
            status=202,
        )
```

(`result_payload` arrives in Task 9 — for this task, guard the import behind the `if wait:` branch as shown and let the timeout test patch it.)

- [ ] **Step 8: Run all three test files to verify they pass**

- [ ] **Step 9: Commit**

```bash
git add backend/agent_kv
git commit -m "feat(agent-kv): staging, executor dispatch glue, submit view"
```

---

### Task 9: Status, result, cancel, delete endpoints

**Files:**
- Create: `backend/agent_kv/execution_views_result.py`
- Modify: `backend/agent_kv/execution_views.py`, `backend/agent_kv/execution_urls.py`
- Test: `backend/agent_kv/tests/test_job_views.py`

**Interfaces:**
- Consumes: `AgentKVJob` (Task 3), `JobNotFound` (Task 5), `storage.read_result`/`delete_job_files` (Task 8), limiter release (Task 7).
- Produces:
  - `GET /{prefix}/{job_id}` → status document (spec §7.2): `job_id`, `status` (lowercased), `stage`, `stages` (list built from the `stages` JSON in `STAGE_NAMES` order, only stages present), `created_at`, `started_at` (= `dispatched_at`), `completed_at`, `pages_total`, `error` (when failed).
  - `GET /{prefix}/{job_id}/result` → `result_payload(job) -> dict` (also used by Task 8's timeout branch): the stored engine result; 404 if job unknown/foreign-org; 409 `{"status": ...}` if not COMPLETED; 404 if expired (`expires_at < now`) or `result_ref` empty.
  - `POST /{prefix}/{job_id}/cancel` → spec §7.4 semantics: `mark_terminal(CANCELLED)`; 200 `{"status": "cancelled"}` if the guard won, 409 with current status if already terminal.
  - `DELETE /{prefix}/{job_id}` → `delete_job_files(job)`, blank both refs, 204.
  - **Every lookup:** `AgentKVJob.objects.get(id=job_id, organization_id=key.organization_id)` — `DoesNotExist` → `JobNotFound` (404, indistinguishable for unknown vs foreign).

- [ ] **Step 1: Write the failing tests** — cases: (1) status for foreign-org job → 404; (2) status running → stages list ordered per `STAGE_NAMES`, lowercased status; (3) result before completion → 409 with current status; (4) result after `expires_at` → 404; (5) result happy path returns `read_result` payload; (6) cancel on RUNNING → `mark_terminal` called with CANCELLED, 200; (7) cancel on COMPLETED → 409 and result untouched; (8) delete calls `delete_job_files` and blanks refs; (9) every endpoint 401s without a key (loop over the four views with no Authorization header, expect `Forbidden` — the §6.8 regression test).

```python
# Shape (write all nine; two shown):
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from api_v2.exceptions import Forbidden  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from agent_kv import execution_views as ev  # noqa: E402
from agent_kv.models import AgentKVJob, AgentKVKey, JobStatus  # noqa: E402


def _authed(method="get", path="/agent-kv/x"):
    req = getattr(APIRequestFactory(), method)(path)
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    return req


@mock.patch.object(AgentKVJob, "objects")
@mock.patch.object(AgentKVKey, "objects")
def test_foreign_org_job_is_404(m_keys, m_jobs):
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    m_jobs.get.side_effect = AgentKVJob.DoesNotExist
    resp = ev.JobStatusView.as_view()(_authed(), job_id=uuid.uuid4())
    assert resp.status_code == 404


def test_all_job_views_401_without_key():
    for view, method in [
        (ev.JobStatusView, "get"), (ev.JobResultView, "get"),
        (ev.JobCancelView, "post"), (ev.JobDeleteView, "delete"),
    ]:
        req = getattr(APIRequestFactory(), method)("/agent-kv/x")
        with pytest.raises(Forbidden):
            view.as_view()(req, job_id=uuid.uuid4())
```

- [ ] **Step 2: Run to verify failure** — ImportError on the new view classes.

- [ ] **Step 3: Implement** — `execution_views_result.py` holds `result_payload(job)` (reads via `storage.read_result`, returns the engine result dict unchanged). Views (`JobStatusView`, `JobResultView`, `JobCancelView`, `JobDeleteView`) in `execution_views.py`, each `@AgentKVKeyValidator.validate_api_key`-decorated with a shared `_get_job(agent_kv_key, job_id)` helper implementing the org-scoped lookup → `JobNotFound`. Status document built exactly per the Interfaces block. URLs:

```python
urlpatterns = [
    path("", SubmitView.as_view(), name="agent_kv_submit"),
    # "validate" is added by Task 10 (its view lands there; adding the route
    # now would break imports at this task's commit).
    path("<uuid:job_id>", JobStatusView.as_view(), name="agent_kv_status"),
    path("<uuid:job_id>/result", JobResultView.as_view(), name="agent_kv_result"),
    path("<uuid:job_id>/cancel", JobCancelView.as_view(), name="agent_kv_cancel"),
]
```

with DELETE handled by method on `JobStatusView`'s URL (`JobStatusView` handles GET, `JobDeleteView` merged as the `delete` method of the same view class — implement one `JobView(APIView)` with `get` and `delete` if simpler; keep the class names in tests aligned with what you build).

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv
git commit -m "feat(agent-kv): status/result/cancel/delete with org-scoped 404s"
```

---

### Task 10: `/validate` endpoint

**Files:**
- Modify: `backend/agent_kv/execution_views.py`, `backend/agent_kv/execution_urls.py` (already routed in Task 9)
- Test: `backend/agent_kv/tests/test_validate_view.py`

**Interfaces:**
- Consumes: `compile_schema`/`SchemaError` (Task 1), `AgentKVKeyValidator` (Task 5), `check_key_rate` (Task 7).
- Produces: `POST /{prefix}/validate` with JSON body `{"keys": {...}}` → 200 `{"valid": true, "leaves": N, "arrays": N, "constraints": N}` or 200 `{"valid": false, "error": "<SchemaError message>"}`. 401 without key; 429 over key rate. No job row, no storage, no dispatch.

- [ ] **Step 1: Write the failing tests** — valid schema → counts; invalid → `valid: false` with the compiler's message verbatim; no key → Forbidden; over rate → 429; body missing `keys` → 400.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** — add the route `path("validate", ValidateView.as_view(), name="agent_kv_validate")` to `execution_urls.py` (immediately after the submit route, BEFORE the `<uuid:job_id>` route), and the view:

```python
class ValidateView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, agent_kv_key=None, **kwargs):
        if not check_key_rate(str(agent_kv_key.id)):
            raise RateLimited()
        spec = request.data.get("keys")
        if spec is None:
            return Response({"detail": "body must include 'keys'"}, status=400)
        try:
            compiled = compile_schema(spec)
        except SchemaError as e:
            return Response({"valid": False, "error": str(e)}, status=200)
        return Response(
            {"valid": True, "leaves": len(compiled.key_specs),
             "arrays": len(compiled.array_specs),
             "constraints": len(compiled.constraints)},
            status=200,
        )
```

- [ ] **Step 4: Run tests to verify they pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv
git commit -m "feat(agent-kv): free authenticated schema validation endpoint"
```

---

### Task 11: Internal API — stage reports and finalize

**Files:**
- Create: `backend/agent_kv/internal_views.py`, `backend/agent_kv/internal_urls.py`
- Modify: `backend/backend/internal_base_urls.py` (add `include("agent_kv.internal_urls")` alongside the existing v1 includes, e.g. after the `api_v2.internal_urls` line)
- Test: `backend/agent_kv/tests/test_internal_views.py`

**Interfaces:**
- Consumes: `AgentKVJob.mark_terminal`, `JobStatus`, `STAGE_NAMES` (Task 3), `storage.write_result` (Task 8), limiter release (Task 7). Auth is ambient: `/internal/` is guarded by `InternalAPIAuthMiddleware` (`backend/middleware/internal_api_auth.py`) — the views assume an authenticated internal caller with `X-Organization-ID`.
- Produces (consumed by the executor & callbacks — freeze the paths):
  - `POST /internal/v1/agent-kv/jobs/<uuid:job_id>/stage/` body `{"org_id", "stage", "status": "running"|"done", "seconds"?: float, "counters"?: {}}` → merges into `stages` JSON, sets `stage` and (first report only) flips PENDING/DISPATCHED → RUNNING. **Idempotent**: re-posting the same stage/status overwrites the same entry. Never touches terminal jobs (guard: update queryset excludes TERMINAL; a late stage report after cancel is a 200 no-op).
  - `POST /internal/v1/agent-kv/jobs/<uuid:job_id>/finalize/` body `{"org_id", "success": bool, "result"?: dict, "error"?: str, "usage_summary"?: dict}` → on success: `write_result` then `mark_terminal(COMPLETED, result_ref=..., usage_summary=...)`; on failure: `mark_terminal(FAILED, error=...)`. Always `AgentKVConcurrencyLimiter.release(org_id, job_id)`. Response `{"finalized": bool}` — False when the guard lost (already terminal), which is the idempotent-duplicate case.

- [ ] **Step 1: Write the failing tests** — stage report flips RUNNING once; stage report on CANCELLED job no-ops with 200; duplicate stage report overwrites, not appends; finalize success writes result then guards terminal; finalize duplicate returns `finalized: false` and does NOT rewrite the result; finalize failure records error; both endpoints release the slot... (mock-collaborator style throughout, patch `AgentKVJob.objects`, `storage.write_result`, limiter).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** — plain DRF `APIView`s with empty auth classes (middleware owns auth), reading `org_id` from body and requiring it. Stage merge:

```python
job_qs = AgentKVJob.objects.filter(
    id=job_id, organization_id=org_id
).exclude(status__in=list(AgentKVJob.TERMINAL))
job = job_qs.first()
if job is None:
    return Response({"ok": True, "noop": True})  # late report; terminal guard
stages = dict(job.stages or {})
entry = {"status": body["status"]}
if "seconds" in body:
    entry["seconds"] = body["seconds"]
entry.update(body.get("counters") or {})
stages[body["stage"]] = entry
updates = {"stages": stages, "stage": body["stage"]}
if job.status in (JobStatus.PENDING, JobStatus.DISPATCHED):
    updates["status"] = JobStatus.RUNNING
job_qs.update(**updates)
return Response({"ok": True})
```

Finalize per the Interfaces block, with `release` in a `finally:`.

- [ ] **Step 4: Run tests to verify they pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv backend/backend/internal_base_urls.py
git commit -m "feat(agent-kv): internal stage-report and finalize APIs (idempotent)"
```

---

### Task 12: Workers — callback tasks + queue routing

**Files:**
- Modify: `workers/shared/enums/worker_enums_base.py` (QueueName enum: add `AGENT_KV_CALLBACK = "agent_kv_callback"` to BOTH QueueName-bearing enums in that file if two exist — check line 146 and its sibling)
- Modify: `workers/shared/infrastructure/config/registry.py` (WorkerType.IDE_CALLBACK routes: add `TaskRoute("agent_kv_complete", QueueName.AGENT_KV_CALLBACK)` and `TaskRoute("agent_kv_error", QueueName.AGENT_KV_CALLBACK)`)
- Create: `workers/ide_callback/agent_kv_tasks.py`
- Modify: `workers/ide_callback/worker.py` (import `agent_kv_tasks` the same way `tasks` is imported so Celery registers them)
- Modify: `workers/shared/api/internal_client.py` (two client methods)
- Test: `workers/ide_callback/tests/test_agent_kv_callbacks.py`

**Interfaces:**
- Consumes: internal endpoints (Task 11 paths), `callback_kwargs = {"job_id", "org_id"}` and the executor `result_dict` contract: `{"success": bool, "data": {"output": {...engine result...}, "usage_summary": {...}}, "error": str|None}` (mirror of how `ide_index_complete` reads `result_dict`; the cloud executor produces this — it is frozen here).
- Produces: Celery tasks `agent_kv_complete(result_dict, callback_kwargs)` / `agent_kv_error(request=None, exc=None, traceback=None, callback_kwargs=None)` (error-link signature per Celery's link_error convention — copy `ide_index_error`'s exact parameter list). Both call `InternalAPIClient.agent_kv_finalize(...)`; complete additionally triggers the webhook (Task 13) after finalize succeeds.
- New client methods: `InternalAPIClient.agent_kv_finalize(job_id, org_id, success, result=None, error="", usage_summary=None) -> dict` → POST `/internal/v1/agent-kv/jobs/{job_id}/finalize/`; `InternalAPIClient.agent_kv_get_webhook(job_id, org_id) -> dict` → **not needed**: instead `agent_kv_finalize`'s response includes `{"finalized": bool, "webhook_url": str, "status": str}` — extend Task 11's finalize response to return those two extra fields (modify that view + its tests accordingly in THIS task; it keeps one round-trip).

- [ ] **Step 1: Write the failing tests** — patch `_get_api_client()` (mirror how existing ide_callback tests patch it; if none exist, patch `agent_kv_tasks._get_api_client`): success path calls finalize with `success=True` and the engine result; executor-reported failure (`result_dict["success"] is False`) finalizes with `success=False` and the error; error-link task finalizes `success=False`; webhook fired only when finalize returns `finalized: true` and a non-empty `webhook_url`; webhook NOT fired on duplicate (`finalized: false`).

- [ ] **Step 2: Run to verify failure** — `cd workers && uv run pytest ide_callback/tests/test_agent_kv_callbacks.py -v`.

- [ ] **Step 3: Implement** `agent_kv_tasks.py` (mirror `ide_index_complete`'s structure: `@worker_task(name="agent_kv_complete")`, same client acquisition; keep it thin):

```python
"""Agent-KV terminal callbacks (spec §5.3). Thin: parse, finalize, webhook."""
import logging
from typing import Any

from shared.infrastructure.worker_singleton import worker_task  # match ide_callback/tasks.py's actual import
from shared.utils.webhook_notify import send_webhook

logger = logging.getLogger(__name__)
_UNKNOWN = "Executor failed without an error message"


def _get_api_client():
    from ide_callback.tasks import _get_api_client as base
    return base()


@worker_task(name="agent_kv_complete")
def agent_kv_complete(result_dict: dict[str, Any],
                      callback_kwargs: dict[str, Any] | None = None) -> dict:
    cb = callback_kwargs or {}
    job_id, org_id = cb.get("job_id", ""), cb.get("org_id", "")
    api = _get_api_client()
    if not result_dict.get("success", False):
        error = result_dict.get("error") or _UNKNOWN
        out = api.agent_kv_finalize(job_id, org_id, success=False, error=error)
    else:
        data = result_dict.get("data") or {}
        out = api.agent_kv_finalize(
            job_id, org_id, success=True,
            result=data.get("output") or {},
            usage_summary=data.get("usage_summary"),
        )
    _maybe_webhook(out, job_id)
    return {"job_id": job_id, "finalized": out.get("finalized", False)}


@worker_task(name="agent_kv_error")
def agent_kv_error(request=None, exc=None, traceback=None,
                   callback_kwargs: dict[str, Any] | None = None) -> dict:
    cb = callback_kwargs or {}
    job_id, org_id = cb.get("job_id", ""), cb.get("org_id", "")
    api = _get_api_client()
    out = api.agent_kv_finalize(
        job_id, org_id, success=False,
        error=str(exc) if exc else _UNKNOWN,
    )
    _maybe_webhook(out, job_id)
    return {"job_id": job_id, "finalized": out.get("finalized", False)}


def _maybe_webhook(finalize_response: dict, job_id: str) -> None:
    if not finalize_response.get("finalized"):
        return
    url = finalize_response.get("webhook_url") or ""
    if not url:
        return
    send_webhook(url, {"job_id": job_id,
                       "status": finalize_response.get("status", "")})
```

(Open `workers/ide_callback/tasks.py` first and align the `worker_task` import and `_get_api_client` acquisition with what it actually does — those two lines must match the codebase, not this listing.)

Extend Task 11's finalize response with `webhook_url` and `status` (and update its tests). Add the enum member, the two `TaskRoute`s, and the worker import.

- [ ] **Step 4: Run workers tests to verify they pass.**

- [ ] **Step 5: Note the deploy config** — add to `docker/sample.env` (and the compose service for the ide_callback worker if queues are listed there): the callback worker must consume the `agent_kv_callback` queue in addition to `ide_callback`. Find the env var that sets the ide_callback worker's queues (grep for `ide_callback` in `docker/`) and document the addition in `docs/agent-kv-api.md` (created in Task 15) plus `sample.env`.

- [ ] **Step 6: Commit**

```bash
git add workers docker/sample.env
git commit -m "feat(agent-kv): terminal callbacks on a dedicated callback queue"
```

---

### Task 13: SSRF-guarded webhook sender

**Files:**
- Create: `workers/shared/utils/webhook_notify.py`
- Test: `workers/shared/tests/test_webhook_notify.py` (create `workers/shared/tests/__init__.py` if absent; if a shared-tests dir already exists elsewhere, follow it)

**Interfaces:**
- Produces: `send_webhook(url: str, payload: dict, *, allow_http: bool = False) -> bool` — used by Task 12. Never raises; returns delivered-or-not.

- [ ] **Step 1: Write the failing tests**

```python
from unittest import mock

import pytest

from shared.utils import webhook_notify as wn


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_private_ip_refused(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("10.0.0.5", 443))]
    assert wn.send_webhook("https://internal.example/x", {"a": 1}) is False
    assert not m_requests.post.called


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_metadata_ip_refused(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
    assert wn.send_webhook("https://md.example/x", {}) is False


def test_http_scheme_refused_by_default():
    assert wn.send_webhook("http://example.com/x", {}) is False


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_public_host_posted_no_redirects(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.return_value.status_code = 200
    assert wn.send_webhook("https://example.com/hook", {"job_id": "j"}) is True
    kw = m_requests.post.call_args.kwargs
    assert kw["allow_redirects"] is False
    assert kw["timeout"] == 10


@mock.patch.object(wn, "requests")
@mock.patch.object(wn.socket, "getaddrinfo")
def test_delivery_error_returns_false_never_raises(m_gai, m_requests):
    m_gai.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
    m_requests.post.side_effect = Exception("boom")
    assert wn.send_webhook("https://example.com/hook", {}) is False
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

```python
"""Terminal-state webhook delivery with SSRF guards (spec §6.7).

Residual accepted risk (documented in the spec): DNS is resolved for the
check and again by requests — a rebinding window exists. The payload carries
only {job_id, status}; the response body is never read.
"""
import ipaddress
import json
import logging
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def send_webhook(url: str, payload: dict, *, allow_http: bool = False) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" and not (allow_http and parsed.scheme == "http"):
            logger.warning("webhook refused: scheme %r", parsed.scheme)
            return False
        if not parsed.hostname or not _host_is_public(parsed.hostname):
            logger.warning("webhook refused: non-public host")
            return False
        resp = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT,
            allow_redirects=False,
        )
        return 200 <= resp.status_code < 300
    except Exception:
        logger.warning("webhook delivery failed", exc_info=True)
        return False
```

- [ ] **Step 4: Run tests to verify they pass.**

- [ ] **Step 5: Commit**

```bash
git add workers/shared
git commit -m "feat(agent-kv): SSRF-guarded webhook sender"
```

---

### Task 14: Sweep + TTL cleanup internal endpoints

**Files:**
- Modify: `backend/agent_kv/internal_views.py`, `backend/agent_kv/internal_urls.py`
- Test: `backend/agent_kv/tests/test_sweeps.py`

**Interfaces:**
- Consumes: `AgentKVJob`/`mark_terminal` (Task 3), `storage.delete_job_files` (Task 8), limiter release (Task 7), `settings.AGENT_KV_SWEEP_GRACE_SECONDS`.
- Produces (invoked by the PG-scheduler/reaper periodic mechanism — spec §5.4; registration itself is deploy config, mirroring how the workflow undispatched sweep is driven):
  - `POST /internal/v1/agent-kv/sweep/` — terminalizes PENDING jobs older than the grace with `dispatched_at IS NULL` → FAILED "Job was never dispatched", releases their slots. Returns `{"swept": N}`. Idempotent (guarded terminal writes).
  - `POST /internal/v1/agent-kv/ttl-cleanup/` — for jobs with `expires_at < now` and a non-blank `input_ref` or `result_ref`: `delete_job_files`, blank both refs (`update`), leave the row (audit). Batch-capped at 500 per call. Returns `{"cleaned": N}`. Idempotent (blank refs are skipped next round).

- [ ] **Step 1: Write the failing tests** — sweep: only PENDING+old+undispatched swept (assert queryset filters), each swept job released; ttl-cleanup: expired-with-refs cleaned, refs blanked, non-expired untouched, second run is a no-op.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** — straightforward querysets per the Interfaces block; sweep loop uses `mark_terminal` per job (guard semantics), cleanup uses `.update(input_ref="", result_ref="")` after deletion.

- [ ] **Step 4: Run tests to verify they pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/agent_kv
git commit -m "feat(agent-kv): undispatched sweep and TTL cleanup internal endpoints"
```

---

### Task 15: Docs, env samples, and the full-suite gate

**Files:**
- Create: `docs/agent-kv-api.md`
- Modify: `docker/sample.env` (AGENT_KV_* vars incl. `AGENT_KV_FILE_STORAGE_CREDENTIALS`; callback queue note from Task 12)
- Test: full suite

**Interfaces:** none new — this task documents the frozen contracts.

- [ ] **Step 1: Write `docs/agent-kv-api.md`** covering: auth (key management location + Bearer), the extraction-schema language (adapted from the spec §7 tables and the schema section of this plan — field `keys`, documented as "extraction schema"), submit fields table (copy spec §7.1 verbatim), status/result/cancel/delete/validate endpoints with example curl + example responses, TTL/retention defaults, the 501-when-engine-absent behavior, and the deploy checklist (env vars; callback queue; internal sweep registration; cloud plugin + executor queue).

- [ ] **Step 2: Update `docker/sample.env`** with every `AGENT_KV_*` setting from Task 3 plus `AGENT_KV_FILE_STORAGE_CREDENTIALS`, each with its default and a one-line comment.

- [ ] **Step 3: Run every agent-kv test file** —

```bash
cd unstract/agent-kv-schema && uv run --with pytest pytest tests/ -q
cd ../filesystem && uv run --with pytest pytest tests/test_agent_kv_storage_type.py -q
cd ../../backend && uv run pytest agent_kv/tests/ -q
cd ../workers && uv run pytest ide_callback/tests/test_agent_kv_callbacks.py shared/tests/test_webhook_notify.py -q
```

Expected: all PASS.

- [ ] **Step 4: Run the pre-existing backend test suite for regressions** — `cd backend && uv run pytest global_api_deployment_key/ api_v2/tests/ -q` (the suites touching shared surfaces we modified). Expected: PASS, unchanged.

- [ ] **Step 5: Commit**

```bash
git add docs/agent-kv-api.md docker/sample.env
git commit -m "docs(agent-kv): API reference, env samples, deploy checklist"
```

---

## Self-Review Notes (run before execution)

- **Spec coverage:** §5.1 gating→T8; §5.3 dispatch→T8/T12; §5.4 model/storage/periodics→T3/T8/T14; §6.1 caps/limits/auth→T5/T6/T7; §6.5 cache — engine-side (cloud), no OSS task by design; §6.7 SSRF→T13; §7.1–7.4 endpoints→T8/T9/T10; §8 metering — executor-side (cloud) except `usage_summary` persistence→T11/T12; §10 OSS tests→every task; §11 rollout config→T12/T15.
- **Deliberate deferrals to the cloud-repo plan:** executor plugin, sandbox worker, PageUsage/Usage emission, subscription reserve check invocation (the submit view gains that call when the plugin lands — the probe seam in T8 is where it attaches).
- **Type consistency spot-checks for executors:** `mark_terminal` signature (T3) vs uses (T8/T11/T14); `callback_kwargs` keys (T8) vs reads (T12); finalize response fields (T11 as extended by T12) vs `_maybe_webhook` (T12); `result_payload` (T9) vs import in T8.
