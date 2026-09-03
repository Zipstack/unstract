"""Regression test for UN-3735.

The destination `status` column must be written as the plain string
"SUCCESS"/"ERROR", never the enum repr "FileProcessingStatus.SUCCESS".

Subtlety: ``FileProcessingStatus`` is a ``(str, Enum)``, so the *member* already
compares equal to its value ("SUCCESS"). The bug only shows when the value is
**stringified** on the way into the DB insert (``str(member)`` →
"FileProcessingStatus.SUCCESS"). So these tests assert on ``str(value)`` — what
the DB driver actually persists — not on ``==``.
"""

from shared.enums.status_enums import FileProcessingStatus
from shared.infrastructure.database.utils import TableColumns, WorkerDatabaseUtils


def test_processing_status_success_is_plain_string() -> None:
    values: dict = {}
    WorkerDatabaseUtils._add_processing_columns(
        values, table_info=None, metadata=None, error=None
    )
    assert str(values[TableColumns.STATUS]) == "SUCCESS"
    assert values[TableColumns.STATUS] == FileProcessingStatus.SUCCESS.value
    # It must be a plain str, not the enum member (which stringifies to the repr).
    assert not isinstance(values[TableColumns.STATUS], FileProcessingStatus)


def test_processing_status_error_is_plain_string() -> None:
    values: dict = {}
    WorkerDatabaseUtils._add_processing_columns(
        values, table_info={"status": "STRING"}, metadata=None, error="boom"
    )
    assert str(values[TableColumns.STATUS]) == "ERROR"
    assert values[TableColumns.STATUS] == FileProcessingStatus.ERROR.value
    assert not isinstance(values[TableColumns.STATUS], FileProcessingStatus)
