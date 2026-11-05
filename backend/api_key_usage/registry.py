"""The key types the usage summary counts.

Each type gives the organisation's keys as a queryset whose rows have ``id``,
``is_active`` and ``expires_at``. The open-source types register in this app's
``ready``; a plugin adds its own, for example the cloud's Human Review keys:

    register_key_type("review_api_key", lambda org: ReviewApiKey.objects.filter(...))
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db.models import QuerySet


@dataclass(frozen=True)
class KeyType:
    name: str
    keys: Callable[[Any], QuerySet]


_KEY_TYPES: dict[str, KeyType] = {}


def register_key_type(name: str, keys: Callable[[Any], QuerySet]) -> None:
    """Add a key type, or replace the one registered under ``name``."""
    _KEY_TYPES[name] = KeyType(name, keys)


def key_types() -> list[KeyType]:
    return list(_KEY_TYPES.values())


def register_builtin_key_types() -> None:
    from global_api_deployment_key.models import GlobalApiDeploymentKey
    from platform_api.models import PlatformApiKey
    from platform_audit.actions import TargetType

    register_key_type(
        TargetType.PLATFORM_API_KEY,
        lambda org: PlatformApiKey.objects.filter(organization=org),
    )
    register_key_type(
        TargetType.GLOBAL_API_DEPLOYMENT_KEY,
        lambda org: GlobalApiDeploymentKey.objects.filter(organization=org),
    )
