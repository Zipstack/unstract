"""Unit tests for the LLMWhisperer v2 image-output helper (MUNS-194 / 196).

Covers ZIP extraction/ordering, corrupt-ZIP handling, page-count verification,
collision-safe folder keys, zero-padded naming, FileStorage persistence with
retry + fail-closed semantics, and write/read round-trip content fidelity.

All tests are pure in-memory / temp-dir units: no network, no live service.
"""

import io

import pytest
from _pytest.monkeypatch import MonkeyPatch

from tests.llmw_image_fixtures import (
    CORRUPT_ZIP,
    FlakyFileStorage,
    InMemoryFileStorage,
    make_page_zip,
    minimal_png,
)
from unstract.sdk1.adapters.exceptions import ExtractorError
from unstract.sdk1.adapters.x2text.dto import PageImageReference
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import constants as c
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
    LLMWhispererHelper,
)
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

H = LLMWhispererHelper


class TestZipExtraction:
    def test_extracts_all_pages_ordered(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(3)))
        assert [p for p, _ in pages] == [1, 2, 3]
        assert all(data.startswith(b"\x89PNG") for _, data in pages)

    def test_orders_even_when_archive_unordered(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(4, shuffle=True)))
        assert [p for p, _ in pages] == [1, 2, 3, 4]

    def test_ignores_non_page_entries(self) -> None:
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("page_001.png", minimal_png())
            archive.writestr("readme.txt", b"not a page")
        buffer.seek(0)
        pages = H.extract_page_images_from_zip(buffer)
        assert [p for p, _ in pages] == [1]

    def test_corrupt_zip_raises_extractor_error(self) -> None:
        corrupt = io.BytesIO(CORRUPT_ZIP)
        with pytest.raises(ExtractorError, match="Corrupt or invalid ZIP"):
            H.extract_page_images_from_zip(corrupt)


class TestPageCountVerification:
    def test_matching_count_passes(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(2)))
        H.verify_page_count(pages, processed_page_count=2)  # no raise

    def test_fewer_pages_raises(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(2)))
        with pytest.raises(ExtractorError, match="Page count mismatch"):
            H.verify_page_count(pages, processed_page_count=3)

    def test_more_pages_raises(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(3)))
        with pytest.raises(ExtractorError, match="Page count mismatch"):
            H.verify_page_count(pages, processed_page_count=2)

    def test_none_count_skips_check(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(2)))
        H.verify_page_count(pages, processed_page_count=None)  # no raise


class TestFolderKeyAndNaming:
    def test_folder_key_isolates_runs(self) -> None:
        dir_a = H.build_page_store_dir("/data/out.txt", "/data/in.pdf", "run-A")
        dir_b = H.build_page_store_dir("/data/out.txt", "/data/in.pdf", "run-B")
        assert dir_a != dir_b
        assert "run-A" in dir_a and "run-B" in dir_b
        assert dir_a.endswith("pages")

    def test_folder_key_deterministic_for_same_run(self) -> None:
        first = H.build_page_store_dir("/data/out.txt", "/data/in.pdf", "run-A")
        second = H.build_page_store_dir("/data/out.txt", "/data/in.pdf", "run-A")
        assert first == second

    def test_folder_falls_back_to_input_dir(self) -> None:
        result = H.build_page_store_dir(None, "/docs/in.pdf", "job1")
        assert result.startswith("/docs/")
        assert "job1" in result

    @pytest.mark.parametrize(
        ("page", "expected"),
        [
            (1, "page_001.png"),
            (9, "page_009.png"),
            (42, "page_042.png"),
            (100, "page_100.png"),
            (1234, "page_1234.png"),
        ],
    )
    def test_zero_padding_consistency(self, page: int, expected: str) -> None:
        assert H._page_image_filename(page) == expected


class TestPersistence:
    def test_persists_all_pages_as_ordered_references(self) -> None:
        fs = InMemoryFileStorage(provider=FileStorageProvider.S3)
        pages = [(2, b"two"), (1, b"one"), (3, b"three")]
        refs = H.persist_page_images(fs, "doc/pages", pages)

        assert [r.page_number for r in refs] == [1, 2, 3]
        assert all(isinstance(r, PageImageReference) for r in refs)
        assert refs[0].filename == "page_001.png"
        assert refs[0].path == "doc/pages/page_001.png"
        assert refs[0].size_bytes == len(b"one")
        assert refs[0].provider is FileStorageProvider.S3
        assert len(fs.stored_paths) == 3

    def test_retry_then_success(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(c.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        monkeypatch.setattr(c.WhispererDefaults, "PAGE_STORE_MAX_RETRIES", 3)
        fs = FlakyFileStorage(fail_times=2)  # succeeds on 3rd attempt
        refs = H.persist_page_images(fs, "doc/pages", [(1, b"data")])
        assert len(refs) == 1
        assert fs.attempts_for("doc/pages/page_001.png") == 3

    def test_fail_closed_when_retries_exhausted(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(c.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        monkeypatch.setattr(c.WhispererDefaults, "PAGE_STORE_MAX_RETRIES", 2)
        fs = FlakyFileStorage(fail_always=True)
        with pytest.raises(ExtractorError, match="Failed to persist page image"):
            H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")])
        # Fail-closed: the second page is never attempted after the first fails.
        assert fs.stored_paths == []

    def test_local_write_read_round_trip(self, tmp_path) -> None:  # noqa: ANN001
        fs = FileStorage(provider=FileStorageProvider.LOCAL)
        page_dir = H.build_page_store_dir(
            output_file_path=str(tmp_path / "out.txt"),
            input_file_path=str(tmp_path / "in.pdf"),
            run_key="job-xyz",
        )
        original = [(1, minimal_png()), (2, b"second-page-bytes")]
        refs = H.persist_page_images(fs, page_dir, original)

        for (page_number, data), ref in zip(original, refs, strict=True):
            assert ref.page_number == page_number
            round_tripped = fs.read(path=ref.path, mode="rb")
            assert round_tripped == data


class TestSubmitParams:
    """submit_pdf_to_images sends tag + file_name for service-side usage reports."""

    _CONFIG = {"url": "u", "unstract_key": "k", "tag": "cfgtag"}

    def _patch(self, monkeypatch: MonkeyPatch) -> dict:
        captured: dict = {}
        monkeypatch.setattr(
            H, "_send_raw_request", lambda **kw: captured.update(kw) or object()
        )
        monkeypatch.setattr(H, "_safe_json", lambda _r: {"whisper_hash": "wh1"})
        return captured

    def test_explicit_tag_and_file_name_are_sent(self, monkeypatch: MonkeyPatch) -> None:
        captured = self._patch(monkeypatch)
        wh = H.submit_pdf_to_images(
            self._CONFIG, io.BytesIO(b"pdf"), tag="mytag", file_name="doc.pdf"
        )
        assert wh == "wh1"
        params = captured["params"]
        assert params["tag"] == "mytag"
        assert params["file_name"] == "doc.pdf"
        assert params["format"] == "png"

    def test_tag_falls_back_to_config_and_no_filename(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        captured = self._patch(monkeypatch)
        H.submit_pdf_to_images(self._CONFIG, io.BytesIO(b"pdf"))
        assert captured["params"]["tag"] == "cfgtag"
        assert "file_name" not in captured["params"]

    def test_list_tag_is_normalized(self, monkeypatch: MonkeyPatch) -> None:
        captured = self._patch(monkeypatch)
        H.submit_pdf_to_images(self._CONFIG, io.BytesIO(b"pdf"), tag=["first", "second"])
        assert captured["params"]["tag"] == "first"
