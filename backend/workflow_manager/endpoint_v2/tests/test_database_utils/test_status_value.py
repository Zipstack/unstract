"""Regression test for UN-3735.

The destination `status` column must be written as the plain string
"SUCCESS"/"ERROR", never the enum repr "FileProcessingStatus.SUCCESS".

The backend ``FileProcessingStatus`` is a plain ``Enum``, so a stringified member
renders as "FileProcessingStatus.SUCCESS"; the assertions check ``str(value)`` —
what the DB driver persists. No DB access needed, so ``SimpleTestCase``.
"""

from django.test import SimpleTestCase

from workflow_manager.endpoint_v2.constants import TableColumns
from workflow_manager.endpoint_v2.database_utils import DatabaseUtils


class DestinationStatusValueTests(SimpleTestCase):
    def _status_for(self, error: str | None) -> object:
        values = DatabaseUtils.get_columns_and_values(
            column_mode_str="WRITE_JSON_TO_A_SINGLE_COLUMN",
            data={"k": "v"},
            file_path="f",
            execution_id="e",
            table_info={
                "status": "STRING",
                "error_message": "STRING",
                "data": "STRING",
            },
            error=error,
        )
        return values[TableColumns.STATUS]

    def test_status_success_is_plain_string(self) -> None:
        self.assertEqual(str(self._status_for(None)), "SUCCESS")

    def test_status_error_is_plain_string(self) -> None:
        self.assertEqual(str(self._status_for("boom")), "ERROR")
