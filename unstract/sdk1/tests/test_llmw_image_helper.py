"""Unit tests for the LLMWhisperer v2 image-output helper (MUNS-194 / 196).

Covers ZIP extraction/ordering, corrupt-ZIP handling, page-count verification,
collision-safe folder keys, zero-padded naming, FileStorage persistence with
retry + fail-closed semantics, and write/read round-trip content fidelity.

All tests are pure in-memory / temp-dir units: no network, no live service.
"""

import io
from unittest.mock import MagicMock

import pytest
import requests
from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.adapters.exceptions import ExtractorError
from unstract.sdk1.adapters.x2text.dto import PageImageReference
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import helper as helper_mod
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
    LLMWhispererHelper,
)
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

from tests.llmw_image_fixtures import (
    CORRUPT_ZIP,
    FlakyFileStorage,
    InMemoryFileStorage,
    make_page_zip,
    minimal_png,
)

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

    def test_archive_with_no_page_entries_raises(self) -> None:
        # A well-formed ZIP with no page_*.png entries is a failed extraction,
        # not an empty success — must fail closed.
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", b"not a page")
        buffer.seek(0)
        with pytest.raises(ExtractorError, match="no page images"):
            H.extract_page_images_from_zip(buffer)


class TestPageCountVerification:
    def test_matching_count_passes(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(2)))
        H.verify_page_count(pages, expected_page_count=2)  # no raise

    def test_fewer_pages_raises(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(2)))
        with pytest.raises(ExtractorError, match="Page count mismatch"):
            H.verify_page_count(pages, expected_page_count=3)

    def test_more_pages_raises(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(3)))
        with pytest.raises(ExtractorError, match="Page count mismatch"):
            H.verify_page_count(pages, expected_page_count=2)

    def test_none_count_skips_check(self) -> None:
        pages = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(2)))
        H.verify_page_count(pages, expected_page_count=None)  # no raise


class TestFolderKeyAndNaming:
    def test_folder_isolates_distinct_documents(self) -> None:
        dir_a = H.build_page_store_dir("/data/extract/doc-a.txt", "/data/doc-a.pdf")
        dir_b = H.build_page_store_dir("/data/extract/doc-b.txt", "/data/doc-b.pdf")
        assert dir_a != dir_b
        assert "doc-a" in dir_a and "doc-b" in dir_b
        assert dir_a.endswith("pages")

    def test_folder_stable_across_runs_for_same_document(self) -> None:
        # Keyed on the document stem, not the per-run hash: a re-extraction
        # overwrites its own pages instead of orphaning a fresh tree.
        first = H.build_page_store_dir("/data/extract/doc.txt", "/data/doc.pdf")
        second = H.build_page_store_dir("/data/extract/doc.txt", "/data/doc.pdf")
        assert first == second == "/data/extract/doc/pages"

    def test_folder_falls_back_to_input_when_no_output(self) -> None:
        assert H.build_page_store_dir(None, "/docs/in.pdf") == "/docs/in/pages"

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
        # Patch the class the helper actually holds (helper_mod.WhispererDefaults),
        # so the budget is genuinely pinned regardless of any module reload
        # elsewhere in the suite.
        monkeypatch.setattr(helper_mod.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        monkeypatch.setattr(helper_mod.WhispererDefaults, "PAGE_STORE_MAX_RETRIES", 3)
        fs = FlakyFileStorage(fail_times=2)  # succeeds on 3rd attempt
        refs = H.persist_page_images(fs, "doc/pages", [(1, b"data")])
        assert len(refs) == 1
        assert fs.attempts_for("doc/pages/page_001.png") == 3

    def test_budget_is_pinned_to_two_retries(self, monkeypatch: MonkeyPatch) -> None:
        # Budget 2 == 3 total attempts. A page whose first 3 attempts fail must
        # error — proving the patched budget actually takes effect (with the
        # default budget 3 == 4 attempts, the 4th would have succeeded).
        monkeypatch.setattr(helper_mod.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        monkeypatch.setattr(helper_mod.WhispererDefaults, "PAGE_STORE_MAX_RETRIES", 2)
        fs = FlakyFileStorage(fail_times=3)  # would succeed only on the 4th attempt
        with pytest.raises(ExtractorError, match="Failed to persist page image"):
            H.persist_page_images(fs, "doc/pages", [(1, b"data")])

    def test_fail_closed_when_retries_exhausted(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(helper_mod.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        monkeypatch.setattr(helper_mod.WhispererDefaults, "PAGE_STORE_MAX_RETRIES", 2)
        fs = FlakyFileStorage(fail_always=True)
        with pytest.raises(ExtractorError, match="Failed to persist page image"):
            H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")])
        # Fail-closed: the second page is never attempted after the first fails.
        assert fs.stored_paths == []

    def test_mid_list_failure_cleans_up_written_pages(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # Page 1 succeeds, page 2 always fails -> the partial set must be removed
        # so a failed extraction leaves no orphan pages behind.
        monkeypatch.setattr(helper_mod.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        monkeypatch.setattr(helper_mod.WhispererDefaults, "PAGE_STORE_MAX_RETRIES", 1)
        fs = FlakyFileStorage(fail_times=0, fail_substrings=("page_002",))
        with pytest.raises(ExtractorError, match="Failed to persist page image"):
            H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")])
        assert "doc/pages" in fs.rm_calls  # cleanup invoked
        assert fs.stored_paths == []  # page 1 removed by the cleanup

    def test_reextraction_with_fewer_pages_prunes_stale_trailing_pages(self) -> None:
        # The pages dir is a stable path: a re-extraction that yields fewer
        # pages must not leave the previous run's trailing images behind,
        # where the reader would serve them as part of the new document.
        fs = InMemoryFileStorage(provider=FileStorageProvider.S3)
        H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b"), (3, b"c")])
        refs = H.persist_page_images(fs, "doc/pages", [(1, b"x"), (2, b"y")])

        assert [r.page_number for r in refs] == [1, 2]
        assert sorted(fs.stored_paths) == [
            "doc/pages/page_001.png",
            "doc/pages/page_002.png",
        ]
        assert fs.read(path="doc/pages/page_001.png", mode="rb") == b"x"

    def test_failed_dir_reset_raises_instead_of_serving_stale_pages(self) -> None:
        fs = InMemoryFileStorage(provider=FileStorageProvider.S3)
        H.persist_page_images(fs, "doc/pages", [(1, b"a")])

        def _rm_fails(path: str, recursive: bool = True) -> None:
            raise OSError("permission denied")

        fs.rm = _rm_fails  # type: ignore[method-assign]
        with pytest.raises(ExtractorError, match="clear previous page images"):
            H.persist_page_images(fs, "doc/pages", [(1, b"x")])

    def test_local_write_read_round_trip(self, tmp_path) -> None:  # noqa: ANN001
        fs = FileStorage(provider=FileStorageProvider.LOCAL)
        page_dir = H.build_page_store_dir(
            output_file_path=str(tmp_path / "out.txt"),
            input_file_path=str(tmp_path / "in.pdf"),
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


_NET_CONFIG = {"url": "https://svc.example", "unstract_key": "k"}


def _json_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


class TestRequestDefaults:
    """The shared raw-request path must apply a finite timeout in practice."""

    def test_default_timeout_is_passed_to_requests(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # Behaviour, not signature: patch requests.request and assert the
        # timeout actually handed to it is finite when a caller omits it.
        captured: dict = {}
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        monkeypatch.setattr(requests, "request", lambda **kw: captured.update(kw) or resp)
        H._send_raw_request(config=_NET_CONFIG, method="GET", endpoint="ping")
        assert isinstance(captured["timeout"], int | float)
        assert captured["timeout"] > 0


class TestPollBehavior:
    def test_processed_returns_payload(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            H, "_send_raw_request", lambda **kw: _json_response({"status": "processed"})
        )
        assert H.poll_pdf_to_images_status(_NET_CONFIG, "wh")["status"] == "processed"

    def test_failure_status_raises_immediately(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            H,
            "_send_raw_request",
            lambda **kw: _json_response({"status": "failed", "message": "boom"}),
        )
        with pytest.raises(ExtractorError, match="unexpected status 'failed'"):
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh")

    def test_non_json_body_fails_fast(self, monkeypatch: MonkeyPatch) -> None:
        # A non-JSON/HTML error body -> _safe_json {} -> status "" -> not an
        # intermediate state -> raise on the first poll (no budget-long hang).
        bad = MagicMock()
        bad.json.side_effect = ValueError("no json")
        bad.text = "<html>bad gateway</html>"
        bad.status_code = 502
        monkeypatch.setattr(H, "_send_raw_request", lambda **kw: bad)
        with pytest.raises(ExtractorError, match="unexpected status"):
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh")

    def test_budget_exhaustion_raises_after_max_attempts(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(helper_mod.WhispererDefaults, "IMAGE_POLL_INTERVAL", 0.0)
        monkeypatch.setattr(helper_mod.WhispererDefaults, "IMAGE_POLL_MAX_ATTEMPTS", 3)
        calls = {"n": 0}

        def _sr(**_: object) -> MagicMock:
            calls["n"] += 1
            return _json_response({"status": "processing"})

        monkeypatch.setattr(H, "_send_raw_request", _sr)
        with pytest.raises(ExtractorError, match="did not reach a terminal state"):
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh")
        assert calls["n"] == 3


class TestDownloadAndSubmitBehavior:
    def test_mid_stream_error_maps_to_extractor_error_and_closes(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        resp = MagicMock()
        resp.iter_content.side_effect = requests.exceptions.ChunkedEncodingError("x")
        monkeypatch.setattr(H, "_send_raw_request", lambda **kw: resp)
        with pytest.raises(ExtractorError, match="Failed to download"):
            H.download_pdf_to_images_zip(_NET_CONFIG, "wh")
        resp.close.assert_called_once()  # connection released on failure

    def test_submit_without_whisper_hash_raises(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(
            H, "_send_raw_request", lambda **kw: _json_response({"message": "ok"})
        )
        with pytest.raises(ExtractorError, match="did not return a job id"):
            H.submit_pdf_to_images(_NET_CONFIG, io.BytesIO(b"pdf"))


class TestImageOutputWrite:
    """write_image_output persists the summary to the extract file."""

    def test_writes_summary_to_extract_file(self, tmp_path) -> None:  # noqa: ANN001
        fs = FileStorage(provider=FileStorageProvider.LOCAL)
        refs = [
            PageImageReference(
                page_number=1, path="doc/pages/page_001.png", filename="page_001.png"
            ),
        ]
        out = str(tmp_path / "doc.txt")
        summary = H.build_image_output_summary(refs)

        H.write_image_output(fs=fs, output_file_path=out, summary=summary)

        # Extract file holds the human summary (what image mode indexes); a
        # non-empty extract is what keeps a re-run from re-submitting.
        assert fs.read(path=out, mode="r") == summary

    def test_summary_is_human_readable_not_json(self) -> None:
        refs = [PageImageReference(page_number=1, path="p/page_001.png")]
        summary = H.build_image_output_summary(refs)
        assert "1 page image" in summary
        assert "page_001.png" not in summary  # references never inlined
