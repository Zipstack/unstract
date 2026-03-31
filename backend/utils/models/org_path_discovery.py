"""Shared BFS utility to discover FK paths to Organization.

Used by both OrganizationFilterBackend (view layer) and
OrgAwareManager (model layer) to auto-discover the FK chain
from any model to Organization.

The result is cached per model class — BFS runs only once per model.
"""

import logging
from collections import deque

from django.db import models

logger = logging.getLogger(__name__)

# Module-level cache shared across filter backend and manager
_org_path_cache: dict[type, str | None] = {}

_FK_TYPES = (models.ForeignKey, models.OneToOneField)


def get_org_path(model: type) -> str | None:
    """Get the cached FK path from a model to Organization.

    Returns the ORM lookup path (e.g., "wf_execution__workflow__organization")
    or None if no path exists.
    """
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
