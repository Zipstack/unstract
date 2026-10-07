"""Unit tests for the LLMWhisperer v2 image-output helper (MUNS-194 / 196).

Covers ZIP extraction/ordering, corrupt-ZIP handling, page-count verification,
collision-safe folder keys, zero-padded naming, FileStorage persistence with
retry + fail-closed semantics, and write/read round-trip content fidelity.

All tests are pure in-memory / temp-dir units: no network, no live service.
"""

import io
import uuid
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
    ObjectStoreLikeMemoryFS,
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

        def _rm_fails(path: str) -> None:
            raise OSError("permission denied")

        fs.rm_exact = _rm_fails  # type: ignore[method-assign]
        with pytest.raises(ExtractorError, match="clear previous page images"):
            H.persist_page_images(fs, "doc/pages", [(1, b"x")])

    def test_silently_partial_delete_raises_instead_of_serving_stale_pages(
        self,
    ) -> None:
        # The delete works from a listing, and a stale listing can omit
        # objects — so it can "succeed" while files survive. The writer must
        # detect survivors and refuse to write, else the stale page joins the
        # new set as a trailing page.
        fs = InMemoryFileStorage(provider=FileStorageProvider.S3)
        H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b"), (3, b"c")])

        real_rm_exact = type(fs).rm_exact

        def _rm_leaves_survivor(path: str) -> None:
            real_rm_exact(fs, path)
            fs._files["doc/pages/page_003.png"] = b"c"  # survived the delete

        fs.rm_exact = _rm_leaves_survivor  # type: ignore[method-assign]
        with pytest.raises(ExtractorError, match="survived the pre-write cleanup"):
            H.persist_page_images(fs, "doc/pages", [(1, b"x"), (2, b"y")])

    def test_noop_rm_is_detected_and_write_rejected(self) -> None:
        # Degenerate variant of the above: rm succeeds as a complete no-op
        # (nothing deleted at all). The post-reset verification must reject
        # the write outright — nothing may be written over the old set.
        fs = InMemoryFileStorage(provider=FileStorageProvider.S3)
        H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")])

        fs.rm_exact = lambda path: None  # type: ignore[method-assign]
        with pytest.raises(ExtractorError, match="survived the pre-write cleanup"):
            H.persist_page_images(fs, "doc/pages", [(1, b"x")])
        assert fs.read(path="doc/pages/page_001.png", mode="rb") == b"a"  # untouched

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


class TestPreSubmitPageCap:
    """The cap is checked BEFORE pdf-to-images is submitted.

    pdf-to-images bills every converted page, and the answer-time cap would
    reject the result anyway — so an over-cap document must fail before the
    conversion is paid for, converting nothing.
    """

    @staticmethod
    def _fs_with_pdf(monkeypatch: MonkeyPatch, page_count: int | None) -> MagicMock:
        """FileStorage whose input PDF reports ``page_count`` pages."""
        monkeypatch.setattr(
            H, "_safe_pdf_page_count", staticmethod(lambda _b: page_count)
        )
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"
        return fs

    def test_over_cap_fails_before_submitting(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "20")
        fs = self._fs_with_pdf(monkeypatch, 164)
        submit = MagicMock(name="submit_pdf_to_images")
        monkeypatch.setattr(H, "submit_pdf_to_images", staticmethod(submit))

        with pytest.raises(ExtractorError) as excinfo:
            H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs)

        msg = str(excinfo.value)
        assert "exceeds the 20-page limit" in msg
        assert "164 pages" in msg
        assert "Nothing was converted or billed" in msg
        # The billed call never happened.
        submit.assert_not_called()

    def test_within_cap_proceeds_to_submit(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "20")
        fs = self._fs_with_pdf(monkeypatch, 3)
        submit = MagicMock(name="submit", return_value="hash-1")
        monkeypatch.setattr(H, "submit_pdf_to_images", staticmethod(submit))
        monkeypatch.setattr(H, "poll_pdf_to_images_status", staticmethod(MagicMock()))
        pages = [(n, minimal_png()) for n in (1, 2, 3)]
        monkeypatch.setattr(H, "_download_and_extract", staticmethod(lambda **_k: pages))
        monkeypatch.setattr(H, "persist_page_images", staticmethod(lambda *_a: []))

        whisper_hash, _ = H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs)

        assert whisper_hash == "hash-1"
        submit.assert_called_once()

    def test_unreadable_page_count_still_submits(self, monkeypatch: MonkeyPatch) -> None:
        # Best-effort by design: a PDF we cannot count locally must not be
        # blocked at extraction — the answer-time cap remains the backstop.
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "1")
        fs = self._fs_with_pdf(monkeypatch, None)
        submit = MagicMock(name="submit", return_value="hash-2")
        monkeypatch.setattr(H, "submit_pdf_to_images", staticmethod(submit))
        monkeypatch.setattr(H, "poll_pdf_to_images_status", staticmethod(MagicMock()))
        monkeypatch.setattr(
            H, "_download_and_extract", staticmethod(lambda **_k: [(1, minimal_png())])
        )
        monkeypatch.setattr(H, "persist_page_images", staticmethod(lambda *_a: []))

        H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs)

        submit.assert_called_once()


def _glob_expanding_storage() -> FileStorage:
    """A FileStorage on the delete semantics of GCS / S3 (see above)."""
    storage = FileStorage(provider=FileStorageProvider.LOCAL)
    storage.fs = ObjectStoreLikeMemoryFS()
    return storage


def _bracketed_page_dir() -> str:
    # Mirrors the failing staging path: the directory is named after the
    # uploaded document, here "... [CDIC] ...". Unique per test because the
    # in-memory filesystem is process-global.
    return f"/{uuid.uuid4().hex}/extract/Crystal Ball [CDIC] Feasibility/pages"


class TestPageStoreWithGlobCharacters:
    """Re-extraction must work when the document name contains [ ] * ?.

    Regression: on GCS, re-extracting a document named with "[CDIC]" failed
    with "Failed to clear previous page images" — fs.rm() read "[CDIC]" as a
    glob character class, matched nothing, and raised FileNotFoundError.
    """

    def test_fixture_reproduces_the_globbing_delete(self) -> None:
        # Guards the two tests below: if fsspec ever stops globbing here,
        # they would pass without exercising the bug at all.
        storage = _glob_expanding_storage()
        page_dir = _bracketed_page_dir()
        storage.fs.pipe(f"{page_dir}/page_001.png", b"old")
        with pytest.raises(FileNotFoundError):
            storage.fs.rm(page_dir, recursive=True)
        # ...while a single exact-key delete works, as on gcsfs / s3fs.
        storage.fs.rm_file(f"{page_dir}/page_001.png")
        assert storage.fs.find(page_dir) == []

    def test_reextraction_replaces_the_previous_page_set(self) -> None:
        storage = _glob_expanding_storage()
        page_dir = _bracketed_page_dir()
        for n in (1, 2, 3):
            storage.fs.pipe(f"{page_dir}/page_{n:03d}.png", b"old")

        refs = H.persist_page_images(
            storage, page_dir, [(1, minimal_png()), (2, minimal_png())]
        )

        assert [r.page_number for r in refs] == [1, 2]
        names = sorted(p.rsplit("/", 1)[-1] for p in storage.fs.find(page_dir))
        # The stale third page from the previous, longer run is gone.
        assert names == ["page_001.png", "page_002.png"]
        assert storage.fs.cat_file(f"{page_dir}/page_001.png") == minimal_png()

    def test_answer_time_loader_reads_the_bracketed_set(self) -> None:
        # Round trip: what extraction writes, the vision-answer path must be
        # able to read back. Discovery uses ls() and reads use open(), neither
        # of which globs — pinned so a future change to either can't quietly
        # break documents with these names at prompt time instead.
        from unstract.sdk1.adapters.x2text.page_image_loader import load_page_images

        storage = _glob_expanding_storage()
        page_dir = _bracketed_page_dir()
        H.persist_page_images(storage, page_dir, [(1, minimal_png()), (2, minimal_png())])

        loaded = load_page_images(storage, page_dir)

        assert [p.page_number for p in loaded] == [1, 2]

    def test_failed_write_cleans_up_partial_pages(self, monkeypatch: MonkeyPatch) -> None:
        # The best-effort cleanup used the same globbing rm and only logged
        # its failure — so for these names it silently left partial pages.
        monkeypatch.setattr(helper_mod.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        monkeypatch.setattr(helper_mod.WhispererDefaults, "PAGE_STORE_MAX_RETRIES", 1)
        storage = _glob_expanding_storage()
        page_dir = _bracketed_page_dir()
        real_write = H._write_single_page

        def fail_on_page_two(fs, path, data):  # noqa: ANN001, ANN202
            if path.endswith("page_002.png"):
                raise OSError("simulated storage failure")
            return real_write(fs=fs, path=path, data=data)

        monkeypatch.setattr(H, "_write_single_page", staticmethod(fail_on_page_two))

        with pytest.raises(ExtractorError):
            H.persist_page_images(
                storage, page_dir, [(1, minimal_png()), (2, minimal_png())]
            )

        assert storage.fs.find(page_dir) == []


class TestExtractionTimeByteBudget:
    """The byte budget is enforced at extraction, before anything is stored.

    Previously only the answer-time check enforced it: a document indexed
    successfully, then failed when the user ran a prompt — after they had
    built their prompts around it.
    """

    def test_within_budget_passes(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "1")
        H.verify_page_bytes([(1, b"x" * 400_000), (2, b"x" * 400_000)])

    def test_over_budget_raises_a_clear_error(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "1")
        with pytest.raises(ExtractorError) as excinfo:
            H.verify_page_bytes([(1, b"x" * 700_000), (2, b"x" * 700_000)])
        msg = str(excinfo.value)
        assert "2 page images" in msg
        assert "more than the 1 MB" in msg
        # Honest about cost: sizes are only known after the billed conversion.
        assert "already been billed" in msg

    def test_extraction_fails_before_persisting(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "1")
        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 2))
        monkeypatch.setattr(
            H, "submit_pdf_to_images", staticmethod(MagicMock(return_value="h1"))
        )
        monkeypatch.setattr(H, "poll_pdf_to_images_status", staticmethod(MagicMock()))
        big_pages = [(1, b"x" * 700_000), (2, b"x" * 700_000)]
        monkeypatch.setattr(
            H, "_download_and_extract", staticmethod(lambda **_k: big_pages)
        )
        persist = MagicMock(name="persist_page_images")
        monkeypatch.setattr(H, "persist_page_images", staticmethod(persist))
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        with pytest.raises(ExtractorError):
            H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs)

        persist.assert_not_called()

    @pytest.mark.parametrize("budget_mb", ["1", "2"])
    def test_extraction_and_answer_time_checks_agree(
        self, budget_mb: str, monkeypatch: MonkeyPatch
    ) -> None:
        # Both checks must read the same override. A ~1.4 MB page set fails
        # both under 1 MB and passes both under 2 MB; it must never pass
        # indexing and then fail when a prompt runs.
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            PageImageSetTooLargeError,
            load_page_images,
        )

        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", budget_mb)
        pages = [(1, b"x" * 700_000), (2, b"x" * 700_000)]
        storage = InMemoryFileStorage()
        page_dir = "/data/extract/doc/pages"
        for number, data in pages:
            storage.write(path=f"{page_dir}/page_{number:03d}.png", mode="wb", data=data)

        try:
            H.verify_page_bytes(pages)
            indexing_ok = True
        except ExtractorError:
            indexing_ok = False
        try:
            load_page_images(storage, page_dir)  # no explicit budget
            answer_ok = True
        except PageImageSetTooLargeError:
            answer_ok = False

        assert indexing_ok == answer_ok == (budget_mb == "2")
