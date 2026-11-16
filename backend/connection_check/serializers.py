from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from connection_check.constants import NEVER_TESTED, ConnectionStatus

if TYPE_CHECKING:
    from connection_check.models import Profile


class ConnectionCheckResultSerializer(serializers.Serializer):
    """Body of the test-and-record endpoints."""

    status = serializers.ChoiceField(choices=ConnectionStatus.choices())
    tested_at = serializers.DateTimeField()
    failure_reason = serializers.CharField(allow_null=True)


def profile_status_fields(profile: "Profile") -> dict[str, Any]:
    """Stored-test keys appended to a profile's list and detail rows."""
    result = getattr(profile, "test_result", None)
    if result is None:
        return {
            "last_test_status": NEVER_TESTED,
            "last_tested_at": None,
            "last_failure_reason": None,
            "tested_before_last_change": False,
        }
    return {
        "last_test_status": result.status,
        "last_tested_at": serializers.DateTimeField().to_representation(result.tested_at),
        "last_failure_reason": result.failure_reason,
        "tested_before_last_change": profile.modified_at > result.tested_at,
    }
