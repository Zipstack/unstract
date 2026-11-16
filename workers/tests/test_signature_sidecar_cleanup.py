"""Stale document_insights sidecars must be removed on re-extraction."""

from unittest.mock import MagicMock

from executor.executors.legacy_executor import LegacyExecutor


def test_empty_signature_data_removes_stale_sidecar() -> None:
    fs = MagicMock()
    fs.exists.return_value = True
    LegacyExecutor._write_signature_sidecar(fs, "/a/doc.txt", None, None)
    fs.rm.assert_called_once_with("/a/doc.doc_insights.json")


def test_empty_signature_data_without_sidecar_is_noop() -> None:
    fs = MagicMock()
    fs.exists.return_value = False
    LegacyExecutor._write_signature_sidecar(fs, "/a/doc.txt", {}, {})
    fs.rm.assert_not_called()
