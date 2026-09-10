"""Shared BFS utility to discover FK paths to Organization.

Used by both OrganizationFilterBackend (view layer) and
OrgAwareManager (model layer) to auto-discover the FK chain
from any model to Organization.

The result is cached per model class — BFS runs only once per model.
"""

import logging
from collections import deque
from collections.abc import Mapping
from types import MappingProxyType

from django.db import models

logger = logging.getLogger(__name__)

# Module-level cache shared across filter backend and manager
_org_path_cache: dict[type, str | None] = {}

_FK_TYPES = (models.ForeignKey, models.OneToOneField)

# Org paths pinned explicitly, checked before BFS. Keyed by model label
# ("app_label.ModelName") so this module stays import-free of the models.
#
# BFS returns the *shortest* path and breaks ties by field declaration order.
# Reordering two fields can therefore swap in a different path of the same
# length, and if that path runs through a nullable FK the resulting INNER JOIN
# silently drops every row with a NULL — data loss that reads as "missing
# records", not as an error. Pinning freezes the path against that.
#
# What test_org_path_discovery actually asserts: each pin still matches what
# BFS would pick, and every hop on it is non-nullable *unless* listed in that
# module's KNOWN_NULLABLE_HOPS with a reason. Several pins are on that list —
# including every terminal `organization` FK, which DefaultOrganizationMixin
# declares null=True — so "pinned" does not mean "cannot drop rows", it means
# "the rows it drops are known and written down".
#
# Precedence, for the two consumers:
#   - OrgAwareManager always uses the pin.
#   - OrganizationFilterBackend checks a viewset's `org_filter_paths` FIRST and
#     only falls back to the pin. A viewset that sets it therefore scopes that
#     model through a different join than its pin. Prefer the pin; reach for
#     `org_filter_paths` only when a model needs OR across several nullable
#     paths, which is why notification_v2 has it.
# Read-only: a wrong entry here is a cross-tenant leak, so the table is not
# something an importer should be able to reach in and change.
ORG_PATH_OVERRIDES: Mapping[str, str] = MappingProxyType(
    {
        "prompt_studio_document_manager_v2.DocumentManager": "tool__organization",
        "prompt_studio_index_manager_v2.IndexManager": (
            "document_manager__tool__organization"
        ),
        "prompt_studio_output_manager_v2.PromptStudioOutputManager": (
            "tool_id__organization"
        ),
        # ToolStudioPrompt.tool_id is nullable — prompts orphaned from their tool
        # are excluded. This is the path already in force.
        "prompt_studio_v2.ToolStudioPrompt": "tool_id__organization",
        # Deliberately not prompt_studio_tool__organization: that FK is nullable,
        # so it would drop tool-less profiles. vector_store is non-null and
        # AdapterInstance is org-owned, so it scopes to the same organization.
        "prompt_profile_manager_v2.ProfileManager": "vector_store__organization",
    }
)


def get_org_path(model: type) -> str | None:
    """Get the cached FK path from a model to Organization.

    Returns the ORM lookup path (e.g., "wf_execution__workflow__organization")
    or None if no path exists.
    """
    pinned = ORG_PATH_OVERRIDES.get(model._meta.label)
    if pinned:
        return pinned

    if model in _org_path_cache:
        return _org_path_cache[model]

    from django.apps import apps

    path = _discover_org_path(model)
    # Cache positive results always.
    # Cache None only after app registry is fully ready — during startup
    # BFS may return None because models aren't loaded yet, so we retry.
    if path is not None or apps.ready:
        _org_path_cache[model] = path
    return path


def _get_fk_fields(model: type):
    """Yield (field_name, related_model) for all FK/OneToOne fields."""
    for field in model._meta.get_fields():
        if isinstance(field, _FK_TYPES) and field.related_model:
            yield field.name, field.related_model


def _discover_org_path(model: type, max_depth: int = 4) -> str | None:
    """BFS through FK relations to find shortest path to Organization.

    Walks the model's FK graph level by level (breadth-first) to find
    the shortest chain of ForeignKey/OneToOneField relations that leads
    to the Organization model.

    Example for ExecutionLog:
        ExecutionLog
          -> wf_execution (FK to WorkflowExecution)
            -> workflow (FK to Workflow)
              -> organization (FK to Organization) <- found!
        Returns: "wf_execution__workflow__organization"

    This path is used as a Django ORM lookup:
        ExecutionLog.objects.filter(wf_execution__workflow__organization=org)

    Args:
        model: The Django model class to start from.
        max_depth: Maximum FK chain depth to traverse (default 4).
            Prevents infinite loops on circular FK relationships.

    Returns:
        ORM lookup path string (e.g., "wf_execution__workflow__organization")
        or None if no path to Organization exists within max_depth.
    """
    from account_v2.models import Organization

    # Check direct field first (depth 0)
    for name, related in _get_fk_fields(model):
        if related is Organization:
            return name

    # BFS for cascade path (depth 1+)
    queue: deque[tuple[type, str]] = deque()
    visited: set[type] = {model}

    for name, related in _get_fk_fields(model):
        if related not in visited:
            visited.add(related)
            queue.append((related, name))

    return _bfs_find_org(queue, visited, Organization, max_depth)


def _bfs_find_org(
    queue: deque[tuple[type, str]],
    visited: set[type],
    target: type,
    max_depth: int,
) -> str | None:
    """Walk the BFS queue to find the target Organization model."""
    while queue:
        current_model, prefix = queue.popleft()

        for name, related in _get_fk_fields(current_model):
            orm_path = f"{prefix}__{name}"

            if related is target:
                return orm_path

            if related not in visited and orm_path.count("__") < max_depth:
                visited.add(related)
                queue.append((related, orm_path))

    return None


def clear_cache():
    """Clear the path cache. Used in tests."""
    _org_path_cache.clear()
