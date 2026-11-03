"""The shared MIME gate must accept whatever LLMWhisperer's gate accepts.

libmagic is not mocked: what it reports for these bytes is the behaviour under
test. Where its container verdicts differ between builds, only the property the
test depends on is asserted.
"""

import io
import zipfile
from unittest import mock

import fsspec
import magic
from shared.exceptions.file_exceptions import UnsupportedMimeTypeError
from shared.workflow.execution.service import WorkerWorkflowExecutionService

from unstract.connectors.constants import Common
from unstract.core import mime_gate
from unstract.core.mime_gate import (
    INCONCLUSIVE_MIME_TYPES,
    SECOND_OPINION_MIME_TYPES,
    classify_file_path,
    classify_stream,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"

_CONTENT_TYPES = (
    '<?xml version="1.0"?><Types>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0"?><Relationships>'
    '<Relationship Id="rId1" Target="xl/workbook.xml" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument"/>'
    "</Relationships>"
)


def _erp_export_bytes() -> bytes:
    """An xlsx whose writer left deleted parts as `[trash]/*.dat` members first.

    That ordering is what makes libmagic describe the file as Microsoft OOXML
    while reporting application/octet-stream for it.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[trash]/0000.dat", b"\x00" * 64)
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("_rels/.rels", _RELS)
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
    return buf.getvalue()


def _classify(data: bytes, chunk_size: int = 64) -> tuple[str | None, bytes]:
    with classify_stream(io.BytesIO(data), chunk_size) as (mime_type, chunks):
        return mime_type, b"".join(chunks)


def test_an_erp_export_is_named_from_the_whole_file(tmp_path) -> None:
    path = tmp_path / "ORDER.xlsx"
    path.write_bytes(_erp_export_bytes())
    assert magic.from_file(str(path), mime=True) in SECOND_OPINION_MIME_TYPES

    assert classify_file_path(str(path)) == XLSX


def test_a_stream_libmagic_cannot_name_from_a_prefix_is_classified_whole() -> None:
    data = _erp_export_bytes()
    assert magic.from_buffer(data[:64], mime=True) in INCONCLUSIVE_MIME_TYPES

    mime_type, copied = _classify(data)

    assert mime_type == XLSX
    assert copied == data


def test_a_stream_named_from_its_prefix_is_not_spilled() -> None:
    data = PDF_BYTES * 8
    with mock.patch.object(mime_gate, "classify_file_path") as whole_file:
        mime_type, copied = _classify(data)

    whole_file.assert_not_called()
    assert mime_type == "application/pdf"
    assert copied == data


def test_an_empty_stream_has_no_type() -> None:
    assert _classify(b"") == (None, b"")


def test_a_pdf_marker_counts_only_within_the_first_1024_bytes(tmp_path) -> None:
    """LLMWhisperer's rule exactly: a bare `%PDF-`, no version, in the window."""
    filler = b"\x00\x01\x02\x03" * 512
    inside = tmp_path / "inside.bin"
    inside.write_bytes(filler[:1000] + b"%PDF-" + filler)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(filler[:1024] + b"%PDF-" + filler)

    assert classify_file_path(str(inside)) == "application/pdf"
    assert classify_file_path(str(outside)) == "application/octet-stream"


def test_an_ole2_verdict_is_not_rescued_by_a_pdf_marker(tmp_path) -> None:
    """LLMWhisperer only looks further after an octet-stream or zip verdict."""
    path = tmp_path / "wrapped.bin"
    path.write_bytes(b"%PDF-1.7" + b"\x00" * 64)
    with mock.patch.object(
        mime_gate.magic, "from_file", return_value="application/x-ole-storage"
    ):
        assert classify_file_path(str(path)) == "application/x-ole-storage"


class _MemoryConnector:
    """A filesystem connector serving the files set on the class."""

    files: dict[str, bytes] = {}

    def __init__(self, settings: dict) -> None:
        pass

    def get_fsspec_fs(self):
        fs = fsspec.filesystem("memory", skip_instance_cache=True)
        fs.store.clear()
        for path, data in self.files.items():
            fs.pipe(path, data)
        return fs


def _copy_from_connector(data: bytes):
    """Run the worker's connector copy on `data`; return (error, bytes written).

    A tiny chunk size, so the copy spans several chunks whichever way the
    first one is classified.
    """
    _MemoryConnector.files = {"/in/ORDER.xlsx": data}
    service = WorkerWorkflowExecutionService(api_client=None)
    storage = mock.MagicMock()
    error = None
    with (
        mock.patch.object(WorkerWorkflowExecutionService, "READ_CHUNK_SIZE", 64),
        mock.patch.object(
            service, "_resolve_connector_config", return_value=("memory", {})
        ),
        mock.patch.dict(
            "unstract.connectors.filesystems.connectors",
            {"memory": {Common.METADATA: {Common.CONNECTOR: _MemoryConnector}}},
        ),
        mock.patch("unstract.filesystem.FileSystem") as file_system,
    ):
        file_system.return_value.get_file_storage.return_value = storage
        try:
            service._copy_filesystem_file(
                file_path="/in/ORDER.xlsx",
                infile_path="exec/INFILE",
                source_file_path="exec/SOURCE",
                file_processing_context=mock.MagicMock(),
                source_connector_id="memory",
                source_config_connector_settings={},
                connector_metadata={},
            )
        except UnsupportedMimeTypeError as exc:
            error = exc
    written = b"".join(
        call.kwargs["data"]
        for call in storage.write.call_args_list
        if call.kwargs["path"] == "exec/INFILE"
    )
    return error, written


def test_a_connector_copy_accepts_an_erp_export() -> None:
    data = _erp_export_bytes()

    error, written = _copy_from_connector(data)

    assert error is None
    assert written == data


def test_a_connector_copy_rejects_before_writing_anything() -> None:
    wav = b"RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x02\x00" * 8

    error, written = _copy_from_connector(wav)

    assert error is not None
    assert written == b""
