"""Writer/reader path-agreement tests for the shared page-image contract.

The adapter (writer) and any page-image reader must derive the
``{extract_dir}/{stem}/pages`` directory through the single shared
``build_page_store_dir`` helper, and discover/order pages via the shared
naming constants. These tests pin that contract: pure functions and
constants only — no I/O, no network, no adapter/consumer classes.
"""

import re

import pytest
from unstract.sdk1.adapters.x2text.constants import (
    ImageOutputConstants,
    build_page_store_dir,
)

# (output_file_path, input_file_path, expected) — expected derives from the
# output path's stem when present (the extract-file discriminator).
_PATH_CASES = [
    pytest.param(
        "/data/extract/doc.txt", "/in/doc.pdf", "/data/extract/doc/pages", id="flat"
    ),
    pytest.param(
        "/a/b/c/d/extract/report.txt",
        "/uploads/report.pdf",
        "/a/b/c/d/extract/report/pages",
        id="nested-output-dir",
    ),
    pytest.param(
        "/data/report.v2.final.txt",
        "/in/report.v2.final.pdf",
        "/data/report.v2.final/pages",
        id="stem-with-dots",
    ),
    pytest.param(
        "/data/annual report (2026).txt",
        "/in/annual report (2026).pdf",
        "/data/annual report (2026)/pages",
        id="stem-with-spaces-and-specials",
    ),
    pytest.param("/data/x.txt", "/in/x.pdf", "/data/x/pages", id="single-char-stem"),
    pytest.param(
        None, "/in/scan.pdf", "/in/scan/pages", id="no-output-path-falls-back-to-input"
    ),
]


class TestBuildPageStoreDir:
    @pytest.mark.parametrize(("output_path", "input_path", "expected"), _PATH_CASES)
    def test_expected_path_and_determinism(
        self, output_path: str | None, input_path: str, expected: str
    ) -> None:
        first = build_page_store_dir(output_path, input_path)
        second = build_page_store_dir(output_path, input_path)
        assert first == expected
        assert first == second  # pure + deterministic

    @pytest.mark.parametrize(("output_path", "input_path", "expected"), _PATH_CASES)
    def test_path_ends_with_pages_subfolder(
        self, output_path: str | None, input_path: str, expected: str
    ) -> None:
        result = build_page_store_dir(output_path, input_path)
        assert result.split("/")[-1] == ImageOutputConstants.PAGES_SUBFOLDER

    def test_writer_and_reader_share_one_implementation(self) -> None:
        # The adapter exposes the helper as a staticmethod bound to the very
        # same shared function — identity, not a reimplementation. Any reader
        # importing from the shared surface therefore agrees byte-for-byte.
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
            LLMWhispererHelper,
        )

        assert LLMWhispererHelper.build_page_store_dir is build_page_store_dir


class TestPageNamingConstants:
    @pytest.mark.parametrize(
        ("filename", "captured"),
        [
            ("page_001.png", "001"),
            ("page_042.png", "042"),
            ("page_100.png", "100"),
            ("page_999.png", "999"),
            # Past page 999 the writer naturally emits 4+ digits — the
            # regex must keep matching (a 3-digit-only pattern would
            # silently drop pages of very large documents).
            ("page_1000.png", "1000"),
        ],
    )
    def test_number_regex_captures_page_index(self, filename: str, captured: str) -> None:
        match = re.search(ImageOutputConstants.PAGE_NUMBER_REGEX, filename)
        assert match is not None
        assert match.group(1) == captured

    @pytest.mark.parametrize(
        "filename", ["thumbnail.png", "page_abc.png", "page_.png", "page_001.jpg"]
    )
    def test_number_regex_rejects_non_page_files(self, filename: str) -> None:
        assert re.fullmatch(ImageOutputConstants.PAGE_NUMBER_REGEX, filename) is None

    def test_natural_sort_via_captured_int(self) -> None:
        # The reason the regex exists: integer sort of the captured group
        # orders pages correctly where lexicographic sort fails past the
        # zero-padding width.
        names = ["page_1000.png", "page_999.png", "page_010.png", "page_001.png"]
        page_re = re.compile(ImageOutputConstants.PAGE_NUMBER_REGEX)
        ordered = sorted(names, key=lambda n: int(page_re.search(n).group(1)))
        assert ordered == [
            "page_001.png",
            "page_010.png",
            "page_999.png",
            "page_1000.png",
        ]
        # Lexicographic order puts page_1000 before page_999 — the misorder
        # the integer sort exists to prevent.
        assert sorted(names) != ordered


class TestWriterFilenamesMatchReaderContract:
    def test_writer_filename_matches_reader_regex(self) -> None:
        # The writer's filename builder must produce names the reader-side
        # regex discovers and parses — the two halves of the contract.
        from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
            LLMWhispererHelper,
        )

        for page in (1, 42, 999, 1000):
            name = LLMWhispererHelper._page_image_filename(page)
            match = re.fullmatch(ImageOutputConstants.PAGE_NUMBER_REGEX, name)
            assert match is not None
            assert int(match.group(1)) == page
