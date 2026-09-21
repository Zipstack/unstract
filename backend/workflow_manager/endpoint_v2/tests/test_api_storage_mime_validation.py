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

import io
import zipfile
from unittest import mock
from unittest.mock import MagicMock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile

import workflow_manager.endpoint_v2.source as src_mod
from workflow_manager.endpoint_v2.constants import ApiDeploymentResultStatus
from workflow_manager.endpoint_v2.source import SourceConnector

# Bytes chosen from what libmagic actually reports (verified against the pinned
# python-magic). A WAV header is the unsupported case: audio/x-wav is neither
# text/* nor a listed type, and RIFF classifies stably on every libmagic build.
# HTML is the opposite case - it looks like something to reject, but it reaches
# the extractor as text/*, so the gate has to let it through.
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
WAV_BYTES = b"RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x02\x00"
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

    A WAV file announced as application/pdf satisfies any header-based check,
    so only sniffing the bytes keeps it out.
    """
    result = _stage([_upload("evil.pdf", WAV_BYTES, "application/pdf")])

    # Never dispatched...
    assert result == {}
    # ...and never written to the bucket.
    collaborators["storage"].write.assert_not_called()


def test_rejection_is_reported_to_the_caller(collaborators) -> None:
    """A rejected file gets its own failed entry in the API response."""
    _stage([_upload("evil.pdf", WAV_BYTES, "application/pdf")])

    collaborators["ResultCacheUtils"].update_api_results.assert_called_once()
    api_result = collaborators["ResultCacheUtils"].update_api_results.call_args.kwargs[
        "api_result"
    ]
    assert api_result.file == "evil.pdf"
    # The message has to name the offending type, not a downstream symptom.
    assert "audio/x-wav" in api_result.error
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
            _upload("evil.pdf", WAV_BYTES, "application/pdf"),
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


def _docx_bytes(pad_first_member: bool) -> bytes:
    """A minimal but genuine OOXML package.

    With `pad_first_member`, `[Content_Types].xml` is no longer the first entry
    — what re-zipping or a streaming writer produces. libmagic then declines to
    name it beyond `application/zip`, which is the shape that has to be resolved
    by looking inside rather than by asking libmagic again.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        if pad_first_member:
            archive.writestr("junk.bin", bytes(range(256)) * 4)
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        archive.writestr("word/document.xml", '<?xml version="1.0"?><document/>')
    return buf.getvalue()


@pytest.mark.parametrize("repackaged", [False, True], ids=["normal", "repackaged"])
def test_real_ooxml_bytes_are_accepted(collaborators, repackaged: bool) -> None:
    """Real container bytes, with libmagic unmocked.

    Every other container test scripts libmagic's answers, so none of them would
    notice the detector asking a question libmagic cannot answer. A repackaged
    OOXML package reads as a bare zip however many bytes it is given, so it is
    the case that proves the resolution works rather than the mocks agreeing
    with each other.
    """
    data = _docx_bytes(pad_first_member=repackaged)

    result = _stage([_upload("report.docx", data, "application/pdf")])

    assert set(result) == {"report.docx"}
    assert result["report.docx"].mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    # Detection copies the upload to classify it; staging must still see it all.
    written = b"".join(
        call.kwargs["data"] for call in collaborators["storage"].write.call_args_list
    )
    assert written == data


def test_an_oversized_mimetype_member_is_not_decompressed(collaborators) -> None:
    """A hostile archive must not turn the type check into a decompression bomb.

    `mimetype` holds one media type string, so a member declaring megabytes is
    not the thing being looked for. Reading it unbounded would materialise
    whatever the archive declares, during synchronous staging, failing the whole
    request before anything is dispatched.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        # Highly compressible, so the archive stays small while the member does not.
        archive.writestr("mimetype", "a" * (8 * 1024 * 1024))
    payload = buf.getvalue()
    assert len(payload) < 100_000  # small on the wire, large on the way out

    result = _stage([_upload("bomb.pdf", payload, "application/pdf")])

    # Not recognised, and never expanded to find that out.
    assert result == {}


def _odf_bytes(declared: str, *, stored: bool = True, first: bool = True) -> bytes:
    """An ODF-shaped archive declaring `declared` in its mimetype member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        if not first:
            archive.writestr("junk.bin", "x" * 64)
        archive.writestr(
            zipfile.ZipInfo("mimetype"),
            declared,
            compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,
        )
        archive.writestr("content.xml", "<office/>")
    return buf.getvalue()


def test_a_genuine_odf_document_is_recognised(collaborators) -> None:
    """The mimetype member identifies which ODF document this is."""
    data = _odf_bytes("application/vnd.oasis.opendocument.text")

    result = _stage([_upload("notes.pdf", data, "application/pdf")])

    assert set(result) == {"notes.pdf"}
    assert result["notes.pdf"].mime_type == "application/vnd.oasis.opendocument.text"


@pytest.mark.parametrize(
    "declared, stored, first, why",
    [
        ("application/pdf", True, True, "names an unrelated format"),
        ("text/plain", True, True, "names a format it cannot vouch for"),
        ("application/vnd.oasis.opendocument.text", False, True, "is compressed"),
        ("application/vnd.oasis.opendocument.text", True, False, "is not first"),
    ],
)
def test_a_mimetype_member_cannot_nominate_a_format(
    collaborators, declared: str, stored: bool, first: bool, why: str
) -> None:
    """The member is archive-controlled, so it may identify but never choose.

    Without this an arbitrary zip declaring an allow-listed type would be waved
    straight through — recreating the deferred extraction failure the whole gate
    exists to prevent. The spec's own conditions are what make it evidence.
    """
    data = _odf_bytes(declared, stored=stored, first=first)

    result = _stage([_upload("spoof.pdf", data, "application/pdf")])

    assert result == {}, f"accepted an archive whose mimetype member {why}"


def test_a_plain_zip_stays_rejected(collaborators) -> None:
    """Looking inside a zip widens recognition, not the allow-list."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("notes.txt", "just a zip of files")
        archive.writestr("data.bin", bytes(range(256)) * 8)

    result = _stage([_upload("archive.pdf", buf.getvalue(), "application/pdf")])

    assert result == {}
    collaborators["storage"].write.assert_not_called()


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

    with mock.patch.object(
        src_mod.magic, "from_buffer", return_value="application/x-ole-storage"
    ) as sniff, mock.patch.object(
        src_mod.magic, "from_file", return_value="application/msword"
    ) as sniff_path:
        result = _stage([_upload("legacy.doc", ole_bytes, "application/msword")])

    # Only the cheap sample came from a buffer...
    assert sniff.call_count == 1
    assert len(sniff.call_args_list[0].args[0]) == SourceConnector.MIME_DETECT_CHUNK_SIZE
    # ...and the verdict came from a path, which is the only way libmagic will
    # name a container.
    assert sniff_path.call_count == 1
    # ...and the answer from the full file is what decides.
    assert set(result) == {"legacy.doc"}
    assert result["legacy.doc"].mime_type == "application/msword"


def test_container_still_rejected_when_the_full_file_is_unsupported(
    collaborators,
) -> None:
    """The full-file re-sniff widens the evidence, not the allow-list."""
    ole_bytes = _ole2_like(SourceConnector.MIME_DETECT_CHUNK_SIZE * 4)
    with mock.patch.object(
        src_mod.magic, "from_buffer", return_value="application/x-ole-storage"
    ), mock.patch.object(
        src_mod.magic, "from_file", return_value="application/x-dosexec"
    ):
        result = _stage([_upload("legacy.doc", ole_bytes, "application/msword")])

    assert result == {}
    collaborators["storage"].write.assert_not_called()


def test_container_upload_is_not_consumed_by_detection(collaborators) -> None:
    """Reading the whole file to classify it must still leave it stageable."""
    ole_bytes = _ole2_like(SourceConnector.MIME_DETECT_CHUNK_SIZE * 4)
    with mock.patch.object(
        src_mod.magic, "from_buffer", return_value="application/x-ole-storage"
    ), mock.patch.object(
        src_mod.magic, "from_file", return_value="application/msword"
    ):
        _stage([_upload("legacy.doc", ole_bytes, "application/msword")])

    written = b"".join(
        call.kwargs["data"] for call in collaborators["storage"].write.call_args_list
    )
    assert written == ole_bytes


def test_undetectable_file_fails_alone(collaborators) -> None:
    """A stream that cannot be read fails its own file, not the whole request."""
    with mock.patch.object(
        SourceConnector,
        "_detect_uploaded_file_mime_type",
        side_effect=[OSError("stream is gone"), "application/pdf"],
    ):
        result = _stage(
            [
                _upload("broken.pdf", PDF_BYTES, "application/pdf"),
                _upload("good.pdf", PDF_BYTES, "application/pdf"),
            ]
        )

    assert set(result) == {"good.pdf"}
    api_result = collaborators["ResultCacheUtils"].update_api_results.call_args.kwargs[
        "api_result"
    ]
    assert api_result.file == "broken.pdf"
    # An I/O fault and an unsupported format need different follow-ups, so the
    # message must not blame the file's type.
    assert "could not determine its type" in api_result.error


def test_disk_backed_upload_is_classified_from_its_temp_file(collaborators) -> None:
    """The branch real legacy-Office uploads actually take must be exercised.

    Django spills anything over FILE_UPLOAD_MAX_MEMORY_SIZE to a
    TemporaryUploadedFile, and .doc/.xls/.ppt are usually over it. Every other
    test here builds a SimpleUploadedFile, which has no temporary_file_path, so
    the in-memory branch is the only one they reach.
    """
    ole_bytes = _ole2_like(SourceConnector.MIME_DETECT_CHUNK_SIZE * 4)
    upload = TemporaryUploadedFile(
        "legacy.doc", "application/msword", len(ole_bytes), None
    )
    upload.write(ole_bytes)
    upload.seek(0)
    assert upload.temporary_file_path()  # the branch under test

    with mock.patch.object(
        src_mod.magic, "from_buffer", return_value="application/x-ole-storage"
    ), mock.patch.object(
        src_mod.magic, "from_file", return_value="application/msword"
    ) as from_file:
        result = _stage([upload])

    # Classified from the path, so a large upload is never buffered whole...
    from_file.assert_called_once_with(upload.temporary_file_path(), mime=True)
    # ...and it is staged with the type the full file resolved to.
    assert set(result) == {"legacy.doc"}
    assert result["legacy.doc"].mime_type == "application/msword"


def test_one_bad_file_survives_a_failing_result_cache(collaborators) -> None:
    """A cache fault while reporting a rejection must not fail the request.

    update_api_results runs inside the staging loop and its pipeline execute is
    unguarded, so letting it escape would mark the whole execution ERROR and
    discard the good files already written.
    """
    collaborators["ResultCacheUtils"].update_api_results.side_effect = Exception(
        "redis is down"
    )

    result = _stage(
        [
            _upload("good.pdf", PDF_BYTES, "application/pdf"),
            _upload("evil.pdf", WAV_BYTES, "application/pdf"),
        ]
    )

    assert set(result) == {"good.pdf"}
    assert _staged_names(collaborators["storage"]) == {"good.pdf"}


def test_systemic_detection_failure_is_not_reported_as_bad_files(
    collaborators,
) -> None:
    """A fault that is not about this file's bytes must fail the request loudly.

    A broken libmagic database or an unreadable temp dir hits every file in
    every request. Swallowing it per-file would answer 200 COMPLETED with every
    file marked invalid, hiding a platform outage behind a clean success.
    """
    with mock.patch.object(
        src_mod.magic, "from_buffer", side_effect=RuntimeError("magic db is broken")
    ):
        with pytest.raises(RuntimeError):
            _stage([_upload("doc.pdf", PDF_BYTES, "application/pdf")])


def test_empty_upload_is_staged_rather_than_called_unsupported(collaborators) -> None:
    """An empty file must reach the downstream empty-file error, not a type error.

    libmagic calls zero bytes application/x-empty, which is absent from
    AllowedFileTypes; without the short-circuit an empty upload would be reported
    as an unsupported type, which names the wrong cause.
    """
    result = _stage([_upload("empty.pdf", b"", "application/pdf")])

    assert set(result) == {"empty.pdf"}
    # No bytes means no type to judge, so the gate is skipped rather than passed.
    assert result["empty.pdf"].mime_type is None
    collaborators["ResultCacheUtils"].update_api_results.assert_not_called()


def test_types_llmwhisperer_supports_are_accepted(collaborators) -> None:
    """The allow-list mirrors what LLMWhisperer can extract.

    HTML and XML look like things to reject and were rejected until the two sets
    were reconciled, but LLMWhisperer extracts both - so rejecting them loses a
    file that would have worked. Accepting what it cannot read and rejecting what
    it can are the same bug in opposite directions.
    """
    result = _stage(
        [
            _upload("page.html", HTML_BYTES, "text/html"),
            _upload("data.xml", b'<?xml version="1.0"?><root><a>1</a></root>', "text/xml"),
        ]
    )

    assert set(result) == {"page.html", "data.xml"}
    assert result["page.html"].mime_type == "text/html"
    collaborators["ResultCacheUtils"].update_api_results.assert_not_called()


def test_pdf_behind_leading_bytes_is_accepted(collaborators) -> None:
    """A PDF that does not start at offset 0 must still be recognised.

    libmagic's PDF rule only matches at offset 0, so eight bytes of padding are
    enough to make a real PDF sniff as application/octet-stream. Extractors
    tolerate the prefix, and LLMWhisperer scans the same window for exactly this
    reason, so rejecting it here would fail a file that works everywhere else -
    including in ETL runs, which share this allow-list.
    """
    wrapped = b"\x00" * 8 + PDF_BYTES

    result = _stage([_upload("wrapped.pdf", wrapped, "application/pdf")])

    assert set(result) == {"wrapped.pdf"}
    assert result["wrapped.pdf"].mime_type == "application/pdf"
    collaborators["ResultCacheUtils"].update_api_results.assert_not_called()


def test_pdf_marker_inside_other_content_does_not_smuggle_a_file_through(
    collaborators,
) -> None:
    """The `%PDF-` rescue must not become a way past the gate.

    Promoting on a bare substring would let any unidentifiable blob carrying
    that text near its start be staged as a PDF, which is the opposite of what
    this check exists for. Re-classifying from the marker's own offset is what
    keeps the rescue narrow.
    """
    # These bytes must actually sniff as application/octet-stream, or the test
    # would pass without ever reaching the rescue it is meant to constrain.
    blob = b"\x00\x01\x02\x03" * 30 + b"%PDF- not really a pdf" + b"\x00\x01\x02\x03" * 100
    assert src_mod.magic.from_buffer(blob, mime=True) == "application/octet-stream"

    result = _stage([_upload("smuggled.pdf", blob, "application/pdf")])

    assert result == {}
    collaborators["storage"].write.assert_not_called()


def test_a_recognised_zip_is_never_promoted_to_pdf(collaborators) -> None:
    """A zip is a zip, whatever its entries happen to contain."""
    with mock.patch.object(
        src_mod.magic, "from_buffer", return_value="application/zip"
    ), mock.patch.object(
        src_mod.magic, "from_file", return_value="application/zip"
    ):
        result = _stage(
            [_upload("archive.pdf", b"PK\x03\x04" + b"%PDF-1.7" * 8, "application/pdf")]
        )

    assert result == {}


def test_unidentifiable_binary_is_rejected(collaborators) -> None:
    """octet-stream is no longer a free pass.

    Anything libmagic cannot name is something LLMWhisperer cannot extract; it
    used to be allow-listed, which is how a zip renamed .pdf reached the
    extractor and came back as a 415.
    """
    with mock.patch.object(
        src_mod.magic, "from_buffer", return_value="application/octet-stream"
    ):
        result = _stage([_upload("mystery.pdf", b"\x00\x01\x02\x03" * 64, "application/pdf")])

    assert result == {}
    collaborators["storage"].write.assert_not_called()
