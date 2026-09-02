"""MIME validation for files staged into API storage.

``SourceConnector.add_input_file_to_api_storage`` is the single funnel through
which API-deployment uploads reach the API storage bucket, so an unsupported
file has to be rejected here or it reaches the extraction step and fails there
with an error that does not name the real cause.

Unit tests: the real classmethod runs with its DB/storage-touching
collaborators patched on the imported module, so no database is needed. MIME
detection itself is deliberately *not* patched — sniffing the bytes with
libmagic is the behaviour under test.
"""

from unittest import mock
from unittest.mock import MagicMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

import workflow_manager.endpoint_v2.source as src_mod
from workflow_manager.endpoint_v2.constants import ApiDeploymentResultStatus
from workflow_manager.endpoint_v2.source import SourceConnector

# Bytes chosen from what libmagic actually reports (verified against the pinned
# python-magic): a PDF header sniffs application/pdf, an HTML document sniffs
# text/html, which is absent from AllowedFileTypes.
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
HTML_BYTES = b"<!DOCTYPE html><html><body>hello</body></html>"


API_STORAGE_DIR = "/api-storage/exec-1"


@pytest.fixture
def collaborators():
    """Patch everything the staging loop touches except MIME detection."""
    with (
        mock.patch.multiple(
            src_mod,
            UserContext=mock.DEFAULT,
            WorkflowLog=mock.DEFAULT,
            Workflow=mock.DEFAULT,
            FileSystem=mock.DEFAULT,
            FileHistoryHelper=mock.DEFAULT,
            ResultCacheUtils=mock.DEFAULT,
        ) as mocks,
        mock.patch.object(
            SourceConnector,
            "get_api_storage_dir_path",
            return_value=API_STORAGE_DIR,
        ),
    ):
        storage = MagicMock()
        mocks["FileSystem"].return_value.get_file_storage.return_value = storage
        mocks["storage"] = storage
        yield mocks


def _upload(name: str, content: bytes, declared: str) -> SimpleUploadedFile:
    """An uploaded file whose declared Content-Type may not match its bytes."""
    return SimpleUploadedFile(name, content, content_type=declared)


def _stage(files):
    return SourceConnector.add_input_file_to_api_storage(
        pipeline_id="pipe-1",
        workflow_id="wf-1",
        execution_id="exec-1",
        file_objs=files,
    )


def _staged_names(storage: MagicMock) -> set[str]:
    """File names that actually had bytes written to API storage."""
    return {
        call.kwargs["path"].rsplit("/", 1)[-1] for call in storage.write.call_args_list
    }


def test_supported_file_is_staged(collaborators) -> None:
    """A real PDF is staged and returned for dispatch."""
    result = _stage([_upload("doc.pdf", PDF_BYTES, "application/pdf")])

    assert set(result) == {"doc.pdf"}
    assert result["doc.pdf"].mime_type == "application/pdf"
    assert _staged_names(collaborators["storage"]) == {"doc.pdf"}


def test_unsupported_bytes_rejected_despite_supported_declared_type(
    collaborators,
) -> None:
    """The declared Content-Type must not decide what reaches the bucket.

    An HTML file announced as application/pdf satisfies any header-based check,
    so only sniffing the bytes keeps it out.
    """
    result = _stage([_upload("evil.pdf", HTML_BYTES, "application/pdf")])

    # Never dispatched...
    assert result == {}
    # ...and never written to the bucket.
    collaborators["storage"].write.assert_not_called()


def test_rejection_is_reported_to_the_caller(collaborators) -> None:
    """A rejected file gets its own failed entry in the API response."""
    _stage([_upload("evil.pdf", HTML_BYTES, "application/pdf")])

    collaborators["ResultCacheUtils"].update_api_results.assert_called_once()
    api_result = collaborators["ResultCacheUtils"].update_api_results.call_args.kwargs[
        "api_result"
    ]
    assert api_result.file == "evil.pdf"
    # The message has to name the offending type, not a downstream symptom.
    assert "text/html" in api_result.error
    assert api_result.status == ApiDeploymentResultStatus.FAILED


def test_missing_declared_type_falls_back_to_sniffed_type(collaborators) -> None:
    """A supported file with no declared Content-Type is still staged.

    The recorded type comes from the bytes, so an absent header neither blocks
    the file nor degrades it to application/octet-stream.
    """
    result = _stage([_upload("doc.pdf", PDF_BYTES, "")])

    assert result["doc.pdf"].mime_type == "application/pdf"


def test_supported_files_survive_a_rejected_sibling(collaborators) -> None:
    """One bad file does not fail the whole request."""
    result = _stage(
        [
            _upload("good.pdf", PDF_BYTES, "application/pdf"),
            _upload("evil.pdf", HTML_BYTES, "application/pdf"),
        ]
    )

    assert set(result) == {"good.pdf"}
    assert _staged_names(collaborators["storage"]) == {"good.pdf"}


def _ole2_like(total_size: int) -> bytes:
    """An OLE2 compound file whose format markers sit past the sample window.

    libmagic resolves .doc/.xls/.ppt through the OLE2 directory sector, which
    lives at the end of the file. Only the container signature is visible in the
    leading bytes, which is exactly the shape that made these files unstageable.
    """
    header = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
    return header + b"\x00" * (total_size - len(header))


def test_container_prefix_triggers_a_full_file_sniff(collaborators) -> None:
    """A container type seen in the sample must not decide the verdict alone.

    Pins the regression directly: an OLE2 upload sniffs application/x-ole-storage
    from its first bytes, which is absent from AllowedFileTypes, so resolving from
    the sample alone rejects every legacy Office file bigger than the window.

    The sniff results are stubbed because libmagic's container reporting differs
    between builds; what must hold everywhere is that an inconclusive sample is
    escalated to the full file instead of being treated as a verdict.
    """
    ole_bytes = _ole2_like(SourceConnector.MIME_DETECT_CHUNK_SIZE * 4)
    sniffs = ["application/x-ole-storage", "application/msword"]

    with mock.patch.object(src_mod.magic, "from_buffer", side_effect=sniffs) as sniff:
        result = _stage([_upload("legacy.doc", ole_bytes, "application/msword")])

    # The sample verdict was inconclusive, so the whole file was classified...
    assert sniff.call_count == 2
    assert len(sniff.call_args_list[0].args[0]) == SourceConnector.MIME_DETECT_CHUNK_SIZE
    assert len(sniff.call_args_list[1].args[0]) == len(ole_bytes)
    # ...and the answer from the full file is what decides.
    assert set(result) == {"legacy.doc"}
    assert result["legacy.doc"].mime_type == "application/msword"


def test_container_still_rejected_when_the_full_file_is_unsupported(
    collaborators,
) -> None:
    """The full-file re-sniff widens the evidence, not the allow-list."""
    ole_bytes = _ole2_like(SourceConnector.MIME_DETECT_CHUNK_SIZE * 4)
    sniffs = ["application/x-ole-storage", "application/x-dosexec"]

    with mock.patch.object(src_mod.magic, "from_buffer", side_effect=sniffs):
        result = _stage([_upload("legacy.doc", ole_bytes, "application/msword")])

    assert result == {}
    collaborators["storage"].write.assert_not_called()


def test_container_upload_is_not_consumed_by_detection(collaborators) -> None:
    """Reading the whole file to classify it must still leave it stageable."""
    ole_bytes = _ole2_like(SourceConnector.MIME_DETECT_CHUNK_SIZE * 4)
    sniffs = ["application/x-ole-storage", "application/msword"]

    with mock.patch.object(src_mod.magic, "from_buffer", side_effect=sniffs):
        _stage([_upload("legacy.doc", ole_bytes, "application/msword")])

    written = b"".join(
        call.kwargs["data"] for call in collaborators["storage"].write.call_args_list
    )
    assert written == ole_bytes


def test_empty_upload_is_staged_rather_than_called_unsupported(collaborators) -> None:
    """An empty file must reach the downstream empty-file error, not a type error.

    libmagic calls zero bytes application/x-empty, which is absent from
    AllowedFileTypes; without the short-circuit an empty upload would be reported
    as an unsupported type, which names the wrong cause.
    """
    result = _stage([_upload("empty.pdf", b"", "application/pdf")])

    assert set(result) == {"empty.pdf"}
    assert result["empty.pdf"].mime_type == "application/octet-stream"
    collaborators["ResultCacheUtils"].update_api_results.assert_not_called()
