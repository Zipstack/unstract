"""Unit tests for the LLMWhisperer v2 image-output helper (MUNS-194 / 196).

Covers ZIP extraction/ordering, corrupt-ZIP handling, page-count verification,
collision-safe folder keys, zero-padded naming, FileStorage persistence with
retry + fail-closed semantics, and write/read round-trip content fidelity.

All tests are pure in-memory / temp-dir units: no network, no live service.
"""

import io
import json
import logging
import uuid
from typing import TYPE_CHECKING
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

if TYPE_CHECKING:
    from unstract.sdk1.utils.image_limits import ImageModePolicy

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

    def test_service_count_is_used_when_local_count_is_unknown(self) -> None:
        two = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(2)))
        three = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(3)))
        H.verify_page_count(two, None, service_page_count=2)  # no raise
        with pytest.raises(ExtractorError, match="reported by the service"):
            H.verify_page_count(three, None, service_page_count=2)

    def test_local_count_wins_over_service_count(self) -> None:
        # An LLMWhisperer that ignored pages_to_extract converts (and bills)
        # the whole document and reports that count: the selection must win.
        three = H.extract_page_images_from_zip(io.BytesIO(make_page_zip(3)))
        with pytest.raises(ExtractorError, match="selected from the input PDF"):
            H.verify_page_count(three, 2, service_page_count=3)

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ({"metadata": {"page_count": 4}}, 4),
            ({}, None),
            ({"metadata": {"page_count": "x"}}, None),
            ({"metadata": {"page_count": 0}}, None),
            ({"metadata": {"page_count": True}}, None),
            ({"metadata": None}, None),
        ],
    )
    def test_status_page_count_reads_metadata(
        self, status: dict, expected: int | None
    ) -> None:
        assert H.status_page_count(status) == expected


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

    def test_document_pages_are_written_as_pages_json(self) -> None:
        fs = InMemoryFileStorage()
        H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")], [10, 12])
        raw = fs.read(path="doc/pages/pages.json", mode="rb")
        assert json.loads(raw) == {"pages": [10, 12]}

    @pytest.mark.parametrize(
        "document_pages",
        [None, [1, 2], [10], [12, 10]],
        ids=["none", "identity", "short", "bad"],
    )
    def test_no_labels_file_without_useful_document_pages(
        self, document_pages: list[int] | None
    ) -> None:
        fs = InMemoryFileStorage()
        H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")], document_pages)
        assert not fs.exists("doc/pages/pages.json")

    @staticmethod
    def _labels_write_fails(fs: InMemoryFileStorage, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setattr(helper_mod.WhispererDefaults, "RETRY_MIN_WAIT", 0.0)
        real_write = fs.write

        def write(path: str, **kwargs: object) -> None:
            if str(path).endswith("pages.json"):
                raise OSError("disk full")
            real_write(path=path, **kwargs)

        monkeypatch.setattr(fs, "write", write)

    def test_labels_write_failure_fails_a_selection_and_removes_the_set(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # Without pages.json a selection would be labelled by position.
        fs = InMemoryFileStorage()
        self._labels_write_fails(fs, monkeypatch)
        with pytest.raises(ExtractorError, match="page labels") as excinfo:
            H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")], [7, 9])
        assert excinfo.value.status_code == 500
        assert not fs.exists("doc/pages/page_001.png")
        assert not fs.exists("doc/pages/page_002.png")

    def test_identity_labels_never_write_so_cannot_fail(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        fs = InMemoryFileStorage()
        self._labels_write_fails(fs, monkeypatch)
        refs = H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")], [1, 2])
        assert [r.page_number for r in refs] == [1, 2]

    def test_labels_round_trip_to_the_vision_message(self) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            build_vision_message_content,
            load_page_images,
        )

        fs = InMemoryFileStorage()
        H.persist_page_images(fs, "doc/pages", [(1, b"a"), (2, b"b")], [10, 12])
        loaded = load_page_images(fs, "doc/pages")
        content = build_vision_message_content(loaded, "Q")
        labels = [b["text"] for b in content[1:] if b["type"] == "text"]
        assert labels == ["Page 10", "Page 12"]

    def test_reextraction_without_labels_removes_old_labels(self) -> None:
        fs = InMemoryFileStorage()
        H.persist_page_images(fs, "doc/pages", [(1, b"a")], [7])
        H.persist_page_images(fs, "doc/pages", [(1, b"a")])
        assert not fs.exists("doc/pages/pages.json")

    @pytest.mark.parametrize(
        ("status", "count", "expected"),
        [
            ({"metadata": {"pages": [4, 9]}}, 2, [4, 9]),
            ({"metadata": {"pages": [4, 9]}}, 3, None),
            ({"metadata": {"pages": [9, 4]}}, 2, None),
            ({"metadata": {}}, 2, None),
            ({}, 2, None),
        ],
    )
    def test_status_document_pages(
        self, status: dict, count: int, expected: list[int] | None
    ) -> None:
        assert H.status_document_pages(status, count) == expected

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

    def test_pages_to_extract_from_config_is_sent(self, monkeypatch: MonkeyPatch) -> None:
        captured = self._patch(monkeypatch)
        config = {**self._CONFIG, "pages_to_extract": " 1-3 , 7 "}
        H.submit_pdf_to_images(config, io.BytesIO(b"pdf"))
        assert captured["params"]["pages_to_extract"] == "1-3,7"

    def test_invalid_pages_to_extract_is_an_extractor_error(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        self._patch(monkeypatch)
        with pytest.raises(ExtractorError) as excinfo:
            H.submit_pdf_to_images(
                {**self._CONFIG, "pages_to_extract": "5-3"}, io.BytesIO(b"pdf")
            )
        assert excinfo.value.status_code == 400

    def test_given_pages_to_extract_overrides_config(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        captured = self._patch(monkeypatch)
        H.submit_pdf_to_images(
            {**self._CONFIG, "pages_to_extract": "bad"},
            io.BytesIO(b"pdf"),
            pages_to_extract="2-4",
        )
        assert captured["params"]["pages_to_extract"] == "2-4"

    @pytest.mark.parametrize(
        ("spec", "total", "expected"),
        [("", 300, 300), ("1-50", 300, 50), ("1-", 5_000_000, 5_000_000)],
    )
    def test_selected_page_count(self, spec: str, total: int, expected: int) -> None:
        assert H.selected_page_count({"pages_to_extract": spec}, total) == expected

    def test_empty_pages_to_extract_is_not_sent(self, monkeypatch: MonkeyPatch) -> None:
        captured = self._patch(monkeypatch)
        H.submit_pdf_to_images({**self._CONFIG, "pages_to_extract": ""}, io.BytesIO(b"x"))
        assert "pages_to_extract" not in captured["params"]


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
        assert "too many pages for image output mode" in msg
        assert "It has 164 pages, and the limit is 20" in msg
        assert "No pages were converted or charged" in msg
        assert "VLM_IMAGE_ANSWER_PAGE_CAP" not in msg
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

    @staticmethod
    def _stub_after_submit(monkeypatch: MonkeyPatch, pages: int) -> MagicMock:
        submit = MagicMock(name="submit", return_value="hash-r")
        monkeypatch.setattr(H, "submit_pdf_to_images", staticmethod(submit))
        monkeypatch.setattr(H, "poll_pdf_to_images_status", staticmethod(MagicMock()))
        images = [(n, minimal_png()) for n in range(1, pages + 1)]
        monkeypatch.setattr(H, "_download_and_extract", staticmethod(lambda **_k: images))
        monkeypatch.setattr(H, "persist_page_images", staticmethod(lambda *_a: []))
        return submit

    def test_range_under_cap_passes_a_large_document(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "20")
        fs = self._fs_with_pdf(monkeypatch, 300)
        submit = self._stub_after_submit(monkeypatch, 10)

        H.get_page_images({"pages_to_extract": "1-10"}, "/in/d.pdf", "/out/d.txt", fs=fs)

        submit.assert_called_once()

    def test_open_range_over_cap_fails_before_submitting(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "20")
        fs = self._fs_with_pdf(monkeypatch, 300)
        submit = self._stub_after_submit(monkeypatch, 300)

        with pytest.raises(ExtractorError) as excinfo:
            H.get_page_images(
                {"pages_to_extract": "1-"}, "/in/d.pdf", "/out/d.txt", fs=fs
            )

        assert "It has 300 pages" in str(excinfo.value)
        submit.assert_not_called()

    @pytest.mark.parametrize("count", [None, 30])
    def test_invalid_range_fails_before_submitting(
        self, monkeypatch: MonkeyPatch, count: int | None
    ) -> None:
        fs = self._fs_with_pdf(monkeypatch, count)
        submit = self._stub_after_submit(monkeypatch, 1)

        with pytest.raises(ExtractorError) as excinfo:
            H.get_page_images(
                {"pages_to_extract": "5-3"}, "/in/d.pdf", "/out/d.txt", fs=fs
            )

        msg = str(excinfo.value)
        assert "'Pages to extract'" in msg
        assert "No pages were converted or charged" in msg
        assert excinfo.value.status_code == 400
        submit.assert_not_called()

    def test_range_past_the_end_fails_before_submitting(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # Valid syntax, but no page of this 30-page PDF is selected.
        fs = self._fs_with_pdf(monkeypatch, 30)
        submit = self._stub_after_submit(monkeypatch, 1)

        with pytest.raises(ExtractorError) as excinfo:
            H.get_page_images(
                {"pages_to_extract": "40-"}, "/in/d.pdf", "/out/d.txt", fs=fs
            )

        assert excinfo.value.status_code == 400
        assert "No pages were converted or charged" in str(excinfo.value)
        submit.assert_not_called()

    @pytest.mark.parametrize("spec", ["1-", "1-999999", "7"])
    def test_unknown_count_checks_the_range_without_expanding_it(
        self, monkeypatch: MonkeyPatch, spec: str
    ) -> None:
        import unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper as helper_mod

        expand = MagicMock(side_effect=AssertionError("must not expand"))
        monkeypatch.setattr(helper_mod, "resolve_page_range", expand)
        config = {"pages_to_extract": spec}
        canonical = H._pages_to_extract_or_error(config)
        assert H._local_selection(config, canonical, None) == (None, None)

    @pytest.mark.parametrize("spec", ["0", "0-3", "5-3", "-0"])
    def test_unknown_count_still_rejects_zero_and_reversed(self, spec: str) -> None:
        with pytest.raises(ExtractorError) as excinfo:
            H._pages_to_extract_or_error({"pages_to_extract": spec})
        assert excinfo.value.status_code == 400

    def test_setting_is_parsed_once_and_passed_to_submit(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        import unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper as helper_mod

        fs = self._fs_with_pdf(monkeypatch, 30)
        submit = self._stub_after_submit(monkeypatch, 3)
        validate = MagicMock(wraps=helper_mod.validate_page_range)
        monkeypatch.setattr(helper_mod, "validate_page_range", validate)

        H.get_page_images({"pages_to_extract": " 1-3 "}, "/in/d.pdf", "/out/d.txt", fs=fs)

        validate.assert_called_once()
        assert submit.call_args.kwargs["pages_to_extract"] == "1-3"

    @pytest.mark.parametrize(
        ("status_pages", "expected"),
        [(None, [10, 12]), ([10, 12], [10, 12]), ([11, 13], [10, 12])],
        ids=["service-missing", "agree", "disagree"],
    )
    def test_labels_use_the_local_selection(
        self,
        monkeypatch: MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        status_pages: list[int] | None,
        expected: list[int],
    ) -> None:
        fs = self._fs_with_pdf(monkeypatch, 30)
        self._stub_after_submit(monkeypatch, 2)
        metadata: dict = {"page_count": 2}
        if status_pages is not None:
            metadata["pages"] = status_pages
        status = {"status": "processed", "metadata": metadata}
        monkeypatch.setattr(
            H, "poll_pdf_to_images_status", staticmethod(lambda *_a: status)
        )
        persist = MagicMock(name="persist", return_value=[])
        monkeypatch.setattr(H, "persist_page_images", staticmethod(persist))

        with caplog.at_level(logging.WARNING):
            H.get_page_images(
                {"pages_to_extract": "10,12"}, "/in/d.pdf", "/out/d.txt", fs=fs
            )

        assert persist.call_args.args[3] == expected
        disagreed = "labelling with the selection" in caplog.text
        assert disagreed == (status_pages == [11, 13])

    def test_over_cap_selection_message_names_the_selection(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "20")
        fs = self._fs_with_pdf(monkeypatch, 300)
        self._stub_after_submit(monkeypatch, 50)
        with pytest.raises(ExtractorError) as excinfo:
            H.get_page_images(
                {"pages_to_extract": "1-50"}, "/in/d.pdf", "/o/d.txt", fs=fs
            )
        msg = str(excinfo.value)
        assert "'Pages to extract' selects 50 of this document's 300 pages" in msg
        assert "It has 50 pages" not in msg and "This document has" not in msg

    def test_status_document_pages_reach_persistence(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        fs = self._fs_with_pdf(monkeypatch, 30)
        self._stub_after_submit(monkeypatch, 2)
        status = {"status": "processed", "metadata": {"page_count": 2, "pages": [10, 12]}}
        monkeypatch.setattr(
            H, "poll_pdf_to_images_status", staticmethod(lambda *_a: status)
        )
        persist = MagicMock(name="persist", return_value=[])
        monkeypatch.setattr(H, "persist_page_images", staticmethod(persist))

        H.get_page_images({"pages_to_extract": "10,12"}, "/in/d.pdf", "/out/d.txt", fs=fs)

        assert persist.call_args.args[3] == [10, 12]

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

        pages = [(1, minimal_png()), (2, minimal_png())]

        with pytest.raises(ExtractorError):
            H.persist_page_images(storage, page_dir, pages)

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
        assert msg.startswith("This document is too large for image output mode.")
        assert "Its 2 page images total 1.3 MiB, over the 1.0 MiB limit" in msg
        # Honest about cost: sizes are only known after the charged conversion.
        assert "already been charged" in msg
        assert "however many pages" not in msg

    def test_env_above_the_fixed_budget_does_not_raise_it(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # The env var is a ceiling: 50 MiB leaves the fixed 14 MiB in force.
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "50")
        with pytest.raises(ExtractorError) as excinfo:
            H.verify_page_bytes([(1, b"x" * 8_000_000), (2, b"x" * 8_000_000)])
        assert "over the 14.0 MiB limit" in str(excinfo.value)

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


def _bedrock_policy(**values: int | None) -> "ImageModePolicy":
    import dataclasses

    from unstract.sdk1.utils.image_limits import ImageModePolicy, resolve_image_limits

    limits = resolve_image_limits("bedrock", "bedrock/anthropic.claude-sonnet-4-5-v1:0")
    for name, value in values.items():
        limits = dataclasses.replace(
            limits, **{name: dataclasses.replace(getattr(limits, name), value=value)}
        )
    return ImageModePolicy.from_limits([limits])


def _stub_flow(
    monkeypatch: MonkeyPatch, pages: list[tuple[int, bytes]]
) -> dict[str, MagicMock]:
    submit = MagicMock(name="submit", return_value="hash-x")
    persist = MagicMock(name="persist_page_images", return_value=[])
    monkeypatch.setattr(H, "submit_pdf_to_images", staticmethod(submit))
    monkeypatch.setattr(H, "poll_pdf_to_images_status", staticmethod(MagicMock()))
    monkeypatch.setattr(H, "_download_and_extract", staticmethod(lambda **_k: pages))
    monkeypatch.setattr(H, "persist_page_images", staticmethod(persist))
    return {"submit": submit, "persist": persist}


class TestModelAwarePreSubmit:
    """With a policy, the pre-submit check uses the model's page budget."""

    def test_over_model_budget_fails_before_submitting_with_a_code(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        from unstract.sdk1.adapters.exceptions import ImageLimitExceededError
        from unstract.sdk1.utils.image_limits import codes

        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 25))
        stubs = _stub_flow(monkeypatch, [])
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        with pytest.raises(ImageLimitExceededError) as excinfo:
            H.get_page_images(
                {}, "/in/doc.pdf", "/out/doc.txt", fs=fs, image_limits=_bedrock_policy()
            )

        err = excinfo.value
        assert isinstance(err, ExtractorError)
        assert err.error_code == codes.IMAGE_PAGE_CAP_EXCEEDED
        assert err.charged is False
        assert err.status_code == 400
        msg = str(err)
        assert "This document has 25 pages" in msg
        assert "Amazon Bedrock" in msg and "20 page images" in msg
        assert "No pages were converted or charged" in msg
        stubs["submit"].assert_not_called()

    def test_page_cap_env_cannot_raise_the_fixed_cap_without_a_policy(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # No policy: the fixed 90 pages. A ceiling above it leaves 90 in force.
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "500")
        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 91))
        stubs = _stub_flow(monkeypatch, [])
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        with pytest.raises(ExtractorError) as excinfo:
            H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs)

        assert "90" in str(excinfo.value)
        stubs["submit"].assert_not_called()

    def test_generous_model_passes_above_the_old_fixed_cap(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        from unstract.sdk1.utils.image_limits import ImageModePolicy, resolve_image_limits

        openai = resolve_image_limits("openai", "openai/gpt-5.6")
        policy = ImageModePolicy.from_limits([openai])
        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 150))
        pages = [(n, minimal_png()) for n in range(1, 151)]
        stubs = _stub_flow(monkeypatch, pages)
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs, image_limits=policy)

        stubs["submit"].assert_called_once()
        stubs["persist"].assert_called_once()

    def test_legacy_env_cap_is_ignored_when_a_policy_is_given(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        from unstract.sdk1.utils.image_limits import ImageModePolicy, resolve_image_limits

        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "2")
        openai = resolve_image_limits("openai", "openai/gpt-5.6")
        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 5))
        stubs = _stub_flow(monkeypatch, [(n, minimal_png()) for n in range(1, 6)])
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        H.get_page_images(
            {},
            "/in/doc.pdf",
            "/out/doc.txt",
            fs=fs,
            image_limits=ImageModePolicy.from_limits([openai]),
        )
        stubs["submit"].assert_called_once()

    def test_size_advisory_is_logged_not_enforced(
        self, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from unstract.sdk1.utils.image_limits import ImageModePolicy, resolve_image_limits

        gemma = resolve_image_limits("bedrock", "bedrock_mantle/google.gemma-4-31b")
        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 15))
        stubs = _stub_flow(monkeypatch, [(n, minimal_png()) for n in range(1, 16)])
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        with caplog.at_level("WARNING"):
            H.get_page_images(
                {},
                "/in/doc.pdf",
                "/out/doc.txt",
                fs=fs,
                image_limits=ImageModePolicy.from_limits([gemma]),
            )
        assert any("may exceed" in r.message for r in caplog.records)
        stubs["submit"].assert_called_once()


class TestModelAwarePostDownload:
    def test_over_request_bytes_fails_before_persisting_and_says_charged(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        from unstract.sdk1.adapters.exceptions import ImageLimitExceededError
        from unstract.sdk1.utils.image_limits import codes

        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 2))
        stubs = _stub_flow(monkeypatch, [(1, b"x" * 600_000), (2, b"x" * 600_000)])
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        with pytest.raises(ImageLimitExceededError) as excinfo:
            H.get_page_images(
                {},
                "/in/doc.pdf",
                "/out/doc.txt",
                fs=fs,
                image_limits=_bedrock_policy(max_request_bytes=1_000_000),
            )
        err = excinfo.value
        assert err.error_code == codes.IMAGE_PAGES_TOO_LARGE
        assert err.charged is True
        assert "already been charged" in str(err)
        stubs["persist"].assert_not_called()

    def test_single_page_over_per_image_limit(self, monkeypatch: MonkeyPatch) -> None:
        from unstract.sdk1.adapters.exceptions import ImageLimitExceededError
        from unstract.sdk1.utils.image_limits import codes

        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 1))
        stubs = _stub_flow(monkeypatch, [(1, b"x" * 200)])
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        with pytest.raises(ImageLimitExceededError) as excinfo:
            H.get_page_images(
                {},
                "/in/doc.pdf",
                "/out/doc.txt",
                fs=fs,
                image_limits=_bedrock_policy(max_image_bytes=100),
            )
        assert excinfo.value.error_code == codes.IMAGE_PAGE_TOO_LARGE
        stubs["persist"].assert_not_called()

    def test_legacy_byte_budget_untouched_without_a_policy(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "1")
        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 2))
        _stub_flow(monkeypatch, [(1, b"x" * 700_000), (2, b"x" * 700_000)])
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"
        with pytest.raises(ExtractorError) as excinfo:
            H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs)
        assert (
            not hasattr(excinfo.value, "error_code") or excinfo.value.error_code is None
        )


class TestMaxTotalImageBytes:
    """LLMWhisperer stops at sdk1's byte budget and rejects unbilled (LW-460)."""

    _CONFIG = {"url": "u", "unstract_key": "k"}

    def _submit_kwargs(
        self,
        monkeypatch: MonkeyPatch,
        page_count: int | None,
        image_limits: "ImageModePolicy | None" = None,
    ) -> dict:
        monkeypatch.setattr(
            H, "_safe_pdf_page_count", staticmethod(lambda _b: page_count)
        )
        submit = MagicMock(name="submit", side_effect=RuntimeError("stop"))
        monkeypatch.setattr(H, "submit_pdf_to_images", staticmethod(submit))
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"
        with pytest.raises(RuntimeError, match="stop"):
            H.get_page_images(
                {}, "/in/doc.pdf", "/out/doc.txt", fs=fs, image_limits=image_limits
            )
        return submit.call_args.kwargs

    def test_submit_sends_the_param(self, monkeypatch: MonkeyPatch) -> None:
        captured: dict = {}
        monkeypatch.setattr(
            H, "_send_raw_request", lambda **kw: captured.update(kw) or object()
        )
        monkeypatch.setattr(H, "_safe_json", lambda _r: {"whisper_hash": "wh1"})
        H.submit_pdf_to_images(self._CONFIG, io.BytesIO(b"pdf"), max_total_image_bytes=7)
        assert captured["params"]["max_total_image_bytes"] == 7
        H.submit_pdf_to_images(self._CONFIG, io.BytesIO(b"pdf"))
        assert "max_total_image_bytes" not in captured["params"]

    def test_fixed_budget_is_sent_without_a_policy(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        kwargs = self._submit_kwargs(monkeypatch, 3)
        assert kwargs["max_total_image_bytes"] == helper_mod.get_fixed_max_total_bytes()

    def test_fixed_budget_sent_is_never_raised_by_the_env(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "50")
        assert H.submit_byte_limit(None, 3) == 14 * 1024 * 1024
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "6")
        assert H.submit_byte_limit(None, 3) == 6 * 1024 * 1024

    def test_policy_budget_for_the_selected_count_is_sent(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        policy = _bedrock_policy()
        expected = policy.raw_byte_budget(page_count=3)
        assert expected is not None and expected > 0
        kwargs = self._submit_kwargs(monkeypatch, 3, policy)
        assert kwargs["max_total_image_bytes"] == expected

    def test_omitted_when_there_is_no_bound(self, monkeypatch: MonkeyPatch) -> None:
        policy = MagicMock(name="policy")
        policy.raw_byte_budget.return_value = None
        assert H.submit_byte_limit(policy, 3) is None
        # A policy's bound needs the page count; unreadable -> omitted.
        assert (
            self._submit_kwargs(monkeypatch, None, _bedrock_policy())[
                "max_total_image_bytes"
            ]
            is None
        )

    @staticmethod
    def _rejected(monkeypatch: MonkeyPatch, metadata: dict) -> None:
        body = {
            "status": "error",
            "message": "error_in_conversion: size_limit_exceeded: ...",
            "metadata": metadata,
        }
        monkeypatch.setattr(H, "_send_raw_request", lambda **kw: _json_response(body))

    _META = {
        "error_code": "size_limit_exceeded",
        "max_total_image_bytes": 20 * 1024 * 1024,
        "rendered_bytes": 21 * 1024 * 1024,
        "pages_rendered": 2,
        "page_count": 5,
    }

    def test_rejection_maps_to_the_fixed_byte_error(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        self._rejected(monkeypatch, self._META)
        with pytest.raises(ExtractorError) as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh")
        assert excinfo.value.status_code == 400
        msg = str(excinfo.value)
        budget_mib = helper_mod.get_fixed_max_total_bytes() / (1024 * 1024)
        assert msg.startswith(
            "This document is too large for image output mode. Its 5 page "
            "images total at least 21.0 MiB, over the "
            f"{budget_mib:.1f} MiB limit for one LLM request. Split the document"
        )
        assert msg.endswith("nothing was charged.")
        assert "already been charged" not in msg

    def test_rejection_maps_to_the_policy_error_and_code(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        from unstract.sdk1.adapters.exceptions import ImageLimitExceededError
        from unstract.sdk1.utils.image_limits import codes
        from unstract.sdk1.utils.image_limits import policy as policy_mod

        policy = _bedrock_policy()
        self._rejected(monkeypatch, self._META)
        with pytest.raises(ImageLimitExceededError) as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh", policy)
        err = excinfo.value
        assert err.error_code == codes.IMAGE_PAGES_TOO_LARGE
        assert err.charged is False and err.status_code == 400
        after_download = policy_mod.request_too_large_message(
            policy,
            page_count=5,
            raw_total=21 * 1024 * 1024,
            prompt_text_bytes=None,
            charged=True,
        )
        msg = str(err)
        assert msg.split(" total at least ")[0] == after_download.split(" total ")[0]
        assert (
            msg.split(" total at least ")[1].split(" Split ")[0]
            == (after_download.split(" total ")[1].split(" Split ")[0])
        )
        assert msg.endswith("nothing was charged.")

    _NO_COUNT = {k: v for k, v in _META.items() if k != "page_count"}

    def test_rejection_without_a_page_count_never_says_zero(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        self._rejected(monkeypatch, self._NO_COUNT)
        with pytest.raises(ExtractorError) as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh")
        msg = str(excinfo.value)
        assert excinfo.value.status_code == 400
        assert " 0 page images" not in msg
        assert "Its page images total at least 21.0 MiB" in msg
        assert msg.endswith("nothing was charged.")

    def test_rejection_without_a_page_count_uses_the_local_count(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        from unstract.sdk1.adapters.exceptions import ImageLimitExceededError

        self._rejected(monkeypatch, self._NO_COUNT)
        with pytest.raises(ImageLimitExceededError) as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh", _bedrock_policy(), 7)
        assert "The 7 page images of this document" in str(excinfo.value)
        self._rejected(monkeypatch, self._NO_COUNT)
        with pytest.raises(ImageLimitExceededError) as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh", _bedrock_policy())
        msg = str(excinfo.value)
        assert " 0 page images" not in msg
        assert "The page images of this document" in msg
        assert excinfo.value.charged is False

    _BAD_FIGURES = {
        "rendered-none": {**_META, "rendered_bytes": None},
        "rendered-missing": {k: v for k, v in _META.items() if k != "rendered_bytes"},
        "rendered-text": {**_META, "rendered_bytes": "22020096"},
        "limit-bool": {**_META, "max_total_image_bytes": True},
        "limit-zero": {**_META, "max_total_image_bytes": 0},
    }

    @pytest.mark.parametrize("case", sorted(_BAD_FIGURES))
    def test_bad_byte_figures_still_give_the_typed_uncharged_error(
        self, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture, case: str
    ) -> None:
        from unstract.sdk1.adapters.exceptions import ImageLimitExceededError
        from unstract.sdk1.utils.image_limits import codes

        metadata = self._BAD_FIGURES[case]
        bad_field = (
            "rendered_bytes" if case.startswith("rendered") else ("max_total_image_bytes")
        )
        expected = (
            "This document is too large for image output mode: LLMWhisperer "
            "stopped converting its pages once they passed the size limit for "
            "one LLM request. Split the document, select fewer pages with "
            "'Pages to extract', or use a text output mode. Nothing was charged."
        )
        self._rejected(monkeypatch, metadata)
        with caplog.at_level("WARNING"), pytest.raises(ExtractorError) as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh")
        assert type(excinfo.value) is ExtractorError
        assert excinfo.value.status_code == 400
        assert str(excinfo.value) == expected
        assert any(
            bad_field in r.getMessage() and r.levelname == "WARNING"
            for r in caplog.records
        )

        self._rejected(monkeypatch, metadata)
        with pytest.raises(ImageLimitExceededError) as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh", _bedrock_policy())
        err = excinfo.value
        assert err.error_code == codes.IMAGE_PAGES_TOO_LARGE
        assert err.charged is False and err.status_code == 400
        assert str(err) == expected

    def test_get_page_images_passes_the_local_count_to_the_poll(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(H, "_safe_pdf_page_count", staticmethod(lambda _b: 3))
        poll = MagicMock(name="poll", return_value={})
        monkeypatch.setattr(
            H, "submit_pdf_to_images", staticmethod(MagicMock(return_value="h"))
        )
        monkeypatch.setattr(H, "poll_pdf_to_images_status", staticmethod(poll))
        images = [(n, minimal_png()) for n in (1, 2, 3)]
        monkeypatch.setattr(H, "_download_and_extract", staticmethod(lambda **_k: images))
        monkeypatch.setattr(H, "persist_page_images", staticmethod(lambda *_a: []))
        fs = MagicMock(name="FileStorage")
        fs.read.return_value = b"%PDF-1.7 fake"

        H.get_page_images({}, "/in/doc.pdf", "/out/doc.txt", fs=fs)

        assert poll.call_args.args[3] == 3

    @pytest.mark.parametrize(
        "metadata",
        [
            {"error_code": "invalid_page_range"},
            {},
        ],
        ids=["other-code", "no-metadata"],
    )
    def test_other_failures_keep_the_generic_error(
        self, monkeypatch: MonkeyPatch, metadata: dict
    ) -> None:
        self._rejected(monkeypatch, metadata)
        with pytest.raises(ExtractorError, match="unexpected status 'error'") as excinfo:
            H.poll_pdf_to_images_status(_NET_CONFIG, "wh")
        assert excinfo.value.status_code == 502
