"""The dashboard's "needs attention" feed (PB-T14).

Each kind of item comes from a provider. OSS registers the failing pipeline and
failing deployment providers from ``DashboardMetricsConfig.ready()``; a cloud
app registers its own kinds from its own ``ready()``, so a kind exists exactly
where its app is installed and OSS never names a cloud kind. The response contract is ``contract/attention-response.schema.json``.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from api_v2.models import APIDeployment
from django.db.models import QuerySet
from pipeline_v2.models import Pipeline
from rest_framework.utils.encoders import JSONEncoder
from workflow_manager.workflow_v2.failing_streaks import FailingStreak, failing_streaks

logger = logging.getLogger(__name__)

# Same pattern the published JSON Schema requires of ``kind``.
_KIND = re.compile(r"^[a-z][a-z0-9_]*$")
# Same pattern the published JSON Schema requires of ``route.key``.
_ROUTE_KEY = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class AttentionItem:
    """One open item.

    ``since`` is when the item began: the first failure of a streak, or the
    oldest wait. ``route`` names a frontend route-registry key and its params;
    the keys are proposed by the global search work (#2343) and not yet merged.
    """

    kind: str
    id: str
    name: str | None
    count: int
    since: datetime | None
    route_key: str | None = None
    route_params: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "count": self.count,
            "since": self.since.isoformat() if self.since else None,
            "route": (
                {"key": self.route_key, "params": self.route_params}
                if self.route_key
                else None
            ),
            "details": self.details,
        }


class AttentionProvider(ABC):
    """Source of one kind of attention item."""

    kind: str
    order: int

    @abstractmethod
    def items(
        self, organization: Any, start_date: datetime, end_date: datetime
    ) -> list[AttentionItem]:
        """Open items of this kind for ``organization`` in the range."""


_providers: dict[str, AttentionProvider] = {}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def register_attention_provider(provider: AttentionProvider) -> None:
    """Register ``provider`` under its ``kind``.

    Re-registering the same class is a no-op, so a repeated ``ready()`` is
    harmless; a different class claiming a taken kind is a wiring bug.
    """
    if not _KIND.fullmatch(provider.kind):
        raise ValueError(f"Invalid attention kind '{provider.kind}'")
    if not _is_int(provider.order):
        raise ValueError(f"Attention kind '{provider.kind}' needs an int order")
    existing = _providers.get(provider.kind)
    if existing is not None:
        if type(existing) is type(provider):
            return
        raise ValueError(
            f"Attention kind '{provider.kind}' is already registered by "
            f"{type(existing).__name__}"
        )
    _providers[provider.kind] = provider


def unregister_attention_provider(kind: str) -> None:
    _providers.pop(kind, None)


def get_attention_providers() -> list[AttentionProvider]:
    """Registered providers in display order."""
    return sorted(_providers.values(), key=lambda p: (p.order, p.kind))


def collect_attention(
    organization: Any, start_date: datetime, end_date: datetime
) -> tuple[list[dict[str, Any]], list[str]]:
    """Every provider's items, serialized, and the kinds whose provider failed.

    A provider fails when it raises, or returns an item that is not of its own
    kind or whose fields do not have the contract's types (``_serialize``). It
    is logged and named, never shown as "nothing needs attention", and the
    other providers' items still return.
    """
    items: list[dict[str, Any]] = []
    failed: list[str] = []
    for provider in get_attention_providers():
        try:
            provided = [
                _serialize(provider, item)
                for item in provider.items(organization, start_date, end_date)
            ]
        except Exception:
            logger.exception(
                "Attention provider '%s' failed for organization %s (%s to %s)",
                provider.kind,
                getattr(organization, "organization_id", organization),
                start_date.isoformat(),
                end_date.isoformat(),
            )
            failed.append(provider.kind)
        else:
            items.extend(provided)
    return items, failed


def _serialize(provider: AttentionProvider, item: AttentionItem) -> dict[str, Any]:
    if item.kind != provider.kind:
        raise ValueError(f"Item of kind '{item.kind}' from provider '{provider.kind}'")
    if not _is_int(item.count) or item.count < 0:
        raise ValueError(f"Item count must be a non-negative int, got {item.count!r}")
    if not isinstance(item.id, str) or not isinstance(item.name, str | None):
        raise ValueError(
            f"Item id must be a string and name a string or None, "
            f"got {item.id!r} and {item.name!r}"
        )
    if not isinstance(item.since, datetime | None) or (
        item.since is not None and item.since.tzinfo is None
    ):
        raise ValueError(f"Item since must be an aware datetime, got {item.since!r}")
    if item.route_key is not None and not _ROUTE_KEY.fullmatch(str(item.route_key)):
        raise ValueError(f"Invalid route key {item.route_key!r}")
    if not isinstance(item.route_params, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in item.route_params.items()
    ):
        raise ValueError(
            f"Route params must map strings to strings: {item.route_params!r}"
        )
    if not isinstance(item.details, dict):
        raise ValueError(f"Item details must be a dict, got {item.details!r}")
    serialized = item.to_dict()
    # Render here, with the encoder the response uses, so a value it cannot
    # encode fails this provider rather than the whole response.
    json.dumps(serialized, cls=JSONEncoder)
    return serialized


class _FailingRowsProvider(AttentionProvider):
    """Rows that ``failing_streaks`` finds failing, latest failure in range.

    Inactive rows are left out: nothing runs them, so nothing needs doing.
    """

    @abstractmethod
    def _rows(self, organization: Any) -> QuerySet[Any]:
        """The org's active rows of this kind."""

    @abstractmethod
    def _item(self, streak: FailingStreak) -> AttentionItem:
        """The item for one failing row."""

    def items(
        self, organization: Any, start_date: datetime, end_date: datetime
    ) -> list[AttentionItem]:
        streaks = failing_streaks(self._rows(organization), start_date, end_date)
        return [self._item(streak) for streak in streaks]

    def _base_item(
        self, streak: FailingStreak, name: str, route_key: str, **details
    ) -> AttentionItem:
        return AttentionItem(
            kind=self.kind,
            id=str(streak.row.pk),
            name=name,
            count=streak.failures_in_a_row,
            since=streak.failing_since,
            route_key=route_key,
            route_params={"id": str(streak.row.pk)},
            details={
                "last_failure": streak.last_failure.isoformat(),
                "last_success": (
                    streak.last_success.isoformat() if streak.last_success else None
                ),
                **details,
            },
        )


class FailingPipelineProvider(_FailingRowsProvider):
    kind = "failing_pipeline"
    order = 10

    _ROUTE_KEYS = {
        Pipeline.PipelineType.ETL: "etl_pipeline.detail",
        Pipeline.PipelineType.TASK: "task_pipeline.detail",
    }

    def _rows(self, organization: Any) -> QuerySet[Any]:
        return Pipeline._base_manager.filter(
            organization=organization,
            active=True,
            pipeline_type__in=list(self._ROUTE_KEYS),
        )

    def _item(self, streak: FailingStreak) -> AttentionItem:
        pipeline = streak.row
        return self._base_item(
            streak,
            pipeline.pipeline_name,
            self._ROUTE_KEYS[pipeline.pipeline_type],
            pipeline_type=pipeline.pipeline_type,
        )


class FailingDeploymentProvider(_FailingRowsProvider):
    kind = "failing_deployment"
    order = 20

    def _rows(self, organization: Any) -> QuerySet[Any]:
        return APIDeployment._base_manager.filter(
            organization=organization, is_active=True
        )

    def _item(self, streak: FailingStreak) -> AttentionItem:
        return self._base_item(streak, streak.row.display_name, "api_deployment.detail")


OSS_PROVIDERS = (FailingPipelineProvider(), FailingDeploymentProvider())
