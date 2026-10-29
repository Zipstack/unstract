import logging
from collections.abc import Callable
from typing import Any

from django.utils import timezone
from rest_framework.exceptions import APIException

from connection_check.constants import (
    MAX_FAILURE_REASON_LENGTH,
    NOT_CONNECTED_REASON,
    UNEXPECTED_FAILURE_REASON,
    ConnectionStatus,
)
from connection_check.models import ConnectionTestResult, Profile

logger = logging.getLogger(__name__)

_UPDATED_FIELDS = ["status", "tested_at", "failure_reason"]


def run_and_record(
    result_model: type[ConnectionTestResult],
    profile: Profile,
    run_test: Callable[[], bool],
) -> ConnectionTestResult:
    """Run ``run_test`` for a saved profile and store the outcome.

    ``tested_at`` is the start time, so an edit made while the test runs
    still reads as a change after the test.
    """
    tested_at = timezone.now()
    status, reason = _run(run_test, profile)
    result = result_model(
        profile=profile,
        organization=profile.organization,
        status=status,
        tested_at=tested_at,
        failure_reason=reason,
    )
    # Upsert, so two tests at once overwrite instead of colliding.
    result_model.objects.bulk_create(
        [result],
        update_conflicts=True,
        unique_fields=["profile"],
        update_fields=_UPDATED_FIELDS,
    )
    logger.info(
        "Recorded connection test for %s %s: %s",
        type(profile).__name__,
        profile.pk,
        status,
    )
    return result


def _run(
    run_test: Callable[[], bool], profile: Profile
) -> tuple[ConnectionStatus, str | None]:
    """Outcome and failure reason of one test run."""
    try:
        connected = run_test()
    except APIException as exc:
        return ConnectionStatus.FAILED, _trim(_detail_text(exc.detail))
    except Exception:
        logger.exception(
            "Connection test errored for %s %s", type(profile).__name__, profile.pk
        )
        return ConnectionStatus.FAILED, UNEXPECTED_FAILURE_REASON
    if connected:
        return ConnectionStatus.CONNECTED, None
    return ConnectionStatus.FAILED, NOT_CONNECTED_REASON


def _detail_text(detail: Any) -> str:
    """Message text of a DRF error detail, which may be nested."""
    if isinstance(detail, dict):
        detail = list(detail.values())
    if isinstance(detail, list):
        return " ".join(_detail_text(item) for item in detail)
    return str(detail)


def _trim(reason: str) -> str:
    return reason[:MAX_FAILURE_REASON_LENGTH]
