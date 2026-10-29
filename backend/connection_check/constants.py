from enum import StrEnum


class ConnectionStatus(StrEnum):
    """Stored outcome of a connection test."""

    CONNECTED = "connected"
    FAILED = "failed"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(status.value, status.name.title()) for status in cls]


# Reported for a profile with no stored result; never stored.
NEVER_TESTED = "never_tested"

MAX_FAILURE_REASON_LENGTH = 500
NOT_CONNECTED_REASON = "The connection test did not succeed."
UNEXPECTED_FAILURE_REASON = (
    "The connection test could not be completed due to an unexpected error."
)


class ListParam:
    """Optional list query parameters and the paged-envelope key."""

    FAILING = "failing"
    LAST_TEST_STATUS = "last_test_status"
    FAILING_COUNT = "failing_count"
