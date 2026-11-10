import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

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
    tested_at: datetime | None = None,
) -> ConnectionTestResult:
    """Run ``run_test`` for a saved profile and return the outcome, storing it
    unless a test that started later is already stored.

    ``tested_at`` is the start time, so an edit made while the test runs
    still reads as a change after the test. Callers pass the time from before
    they loaded the profile; it defaults to now.
    """
    tested_at = tested_at or timezone.now()
    status, reason = _run(run_test, profile)
    result = result_model(
        profile=profile,
        organization=profile.organization,
        status=status,
        tested_at=tested_at,
        failure_reason=reason,
    )
    _store(result_model, result)
    logger.info(
        "Finished connection test for %s %s: %s",
        type(profile).__name__,
        profile.pk,
        status,
    )
    return result


def _store(
    result_model: type[ConnectionTestResult], result: ConnectionTestResult
) -> None:
    """Insert the result, or replace a stored one from a test that started earlier."""
    try:
        result_model.objects.bulk_create([result], ignore_conflicts=True)
    except IntegrityError as exc:
        # Deleted mid-test. The FK is checked at commit, so this needs autocommit.
        logger.warning(
            "%s %s was deleted during its connection test",
            type(result.profile).__name__,
            result.profile.pk,
        )
        raise NotFound() from exc
    result_model.objects.filter(
        profile=result.profile, tested_at__lt=result.tested_at
    ).update(**{field: getattr(result, field) for field in _UPDATED_FIELDS})


def _run(
    run_test: Callable[[], bool], profile: Profile
) -> tuple[ConnectionStatus, str | None]:
    """Outcome and failure reason of one test run."""
    try:
        connected = run_test()
    except APIException as exc:
        # Error text can echo settings; only a 5xx (most adapter errors) logs it.
        logger.warning(
            "Connection test failed for %s %s: %s, status %s",
            type(profile).__name__,
            profile.pk,
            type(exc).__name__,
            exc.status_code,
            exc_info=exc.status_code >= 500,
        )
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
