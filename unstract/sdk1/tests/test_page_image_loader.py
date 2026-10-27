"""Tests for the FileStorage-backed page-image loader (reader side).

Covers discovery + natural ordering (incl. >999 pages), the page cap,
base64 encoding and vision message-block construction, and the typed
empty/partial/duplicate failure modes — across the in-memory S3-like
double and the real local-filesystem FileStorage backend.
"""

import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from unstract.sdk1.adapters.x2text.page_image_loader import (
    DEFAULT_MAX_TOTAL_BYTES,
    DEFAULT_PAGE_CAP,
    MAX_TOTAL_MB_ENV,
    PAGE_CAP_ENV,
    PAGE_LABELS_FILENAME,
    LoadedPageImage,
    PageCapExceededError,
    PageImageSetIncompleteError,
    PageImageSetTooLargeError,
    PageImagesNotFoundError,
    build_vision_message_content,
    discover_page_images,
    fixed_max_total_bytes,
    fixed_page_cap,
    load_page_images,
)
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

from tests.llmw_image_fixtures import InMemoryFileStorage, minimal_png


@pytest.fixture(autouse=True)
def _fresh_bad_env_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each bad env value is logged once per process; start every test fresh.
    from unstract.sdk1.adapters.x2text import page_image_loader

    monkeypatch.setattr(page_image_loader, "_reported_bad_env", set())


if TYPE_CHECKING:
    from unstract.sdk1.utils.image_limits import ImageModePolicy

_DIR = "/data/extract/doc/pages"


def _store(
    pages: dict[int, bytes], extra: dict[str, bytes] | None = None
) -> InMemoryFileStorage:
    fs = InMemoryFileStorage()
    for number, data in pages.items():
        fs.write(path=f"{_DIR}/page_{number:03d}.png", mode="wb", data=data)
    for name, data in (extra or {}).items():
        fs.write(path=f"{_DIR}/{name}", mode="wb", data=data)
    return fs


class TestDiscovery:
    def test_orders_by_integer_page_number(self) -> None:
        fs = _store({n: b"x" for n in (3, 1, 2)})
        assert [n for n, _ in discover_page_images(fs, _DIR)] == [1, 2, 3]

    def test_returns_full_paths(self) -> None:
        fs = _store({1: b"x"})
        assert discover_page_images(fs, _DIR) == [(1, f"{_DIR}/page_001.png")]

    def test_natural_sort_beyond_999_pages(self) -> None:
        # Lexicographic ordering would put page_1000 before page_999.
        fs = InMemoryFileStorage()
        for n in (999, 1000, 1, 1001):
            fs.write(path=f"{_DIR}/page_{n:03d}.png", mode="wb", data=b"x")
        # Fill 2..998 so the set is contiguous.
        for n in range(2, 999):
            fs.write(path=f"{_DIR}/page_{n:03d}.png", mode="wb", data=b"x")
        numbers = [n for n, _ in discover_page_images(fs, _DIR)]
        assert numbers == list(range(1, 1002))

    def test_ignores_non_page_entries(self) -> None:
        fs = _store({1: b"x", 2: b"y"}, extra={"thumbnail.png": b"t", "notes.txt": b"n"})
        assert [n for n, _ in discover_page_images(fs, _DIR)] == [1, 2]


class TestFailureModes:
    def test_missing_directory_raises_not_found(self) -> None:
        with pytest.raises(PageImagesNotFoundError) as excinfo:
            discover_page_images(InMemoryFileStorage(), _DIR)
        # Remediation must steer to cache-bypass re-extraction + billing note.
        assert "cache bypass" in str(excinfo.value)
        assert "billed per page" in str(excinfo.value)

    def test_directory_with_only_foreign_files_raises_not_found(self) -> None:
        fs = _store({}, extra={"thumbnail.png": b"t"})
        with pytest.raises(PageImagesNotFoundError):
            discover_page_images(fs, _DIR)

    def test_partial_set_raises_incomplete_with_missing_pages(self) -> None:
        fs = _store({1: b"a", 2: b"b", 4: b"d", 7: b"g"})
        with pytest.raises(PageImageSetIncompleteError) as excinfo:
            discover_page_images(fs, _DIR)
        err = excinfo.value
        assert err.found_pages == [1, 2, 4, 7]
        assert err.missing_pages == [3, 5, 6]
        assert "cache bypass" in str(err)

    def test_empty_and_partial_are_distinct_types(self) -> None:
        # Callers branch remediation copy on the exception type; neither may
        # be a subclass of the other.
        assert not issubclass(PageImagesNotFoundError, PageImageSetIncompleteError)
        assert not issubclass(PageImageSetIncompleteError, PageImagesNotFoundError)

    def test_duplicate_page_numbers_raise_incomplete(self) -> None:
        fs = _store({1: b"a"})
        # page_001.png and page_1.png parse to the same page number.
        fs.write(path=f"{_DIR}/page_1.png", mode="wb", data=b"dup")
        with pytest.raises(PageImageSetIncompleteError, match="Duplicate"):
            discover_page_images(fs, _DIR)


class TestPageCap:
    def test_within_cap_loads(self) -> None:
        fs = _store({1: b"a", 2: b"b"})
        assert len(load_page_images(fs, _DIR, page_cap=2)) == 2

    def test_over_cap_raises_with_clear_message(self) -> None:
        fs = _store({n: b"x" for n in range(1, 6)})
        with pytest.raises(PageCapExceededError) as excinfo:
            load_page_images(fs, _DIR, page_cap=4)
        err = excinfo.value
        assert err.page_count == 5
        assert err.page_cap == 4
        msg = str(err)
        assert "too many pages for image output mode" in msg
        assert "It has 5 pages, and the limit is 4" in msg
        # Image mode honours the adapter's "Pages to extract" setting, so the
        # message offers narrowing it. The operator-only env var is not shown.
        assert "'Pages to extract' to a smaller range" in msg
        assert "VLM_IMAGE_ANSWER_PAGE_CAP" not in msg

    def test_cap_check_precedes_reads(self) -> None:
        # Fail-fast: no image bytes are read for an oversized document.
        fs = _store({n: b"x" for n in range(1, 6)})
        reads: list[str] = []
        original_read = fs.read
        fs.read = lambda path, **kw: reads.append(path) or original_read(path, **kw)
        with pytest.raises(PageCapExceededError):
            load_page_images(fs, _DIR, page_cap=1)
        # Only the small labels file (read for the message) may be touched.
        assert [p for p in reads if not p.endswith(PAGE_LABELS_FILENAME)] == []

    def test_none_disables_cap(self) -> None:
        fs = _store({n: b"x" for n in range(1, DEFAULT_PAGE_CAP + 5)})
        loaded = load_page_images(fs, _DIR, page_cap=None)
        assert len(loaded) == DEFAULT_PAGE_CAP + 4


class TestLoadingAndEncoding:
    def test_base64_round_trip(self) -> None:
        payload = minimal_png()
        fs = _store({1: payload})
        [loaded] = load_page_images(fs, _DIR)
        assert isinstance(loaded, LoadedPageImage)
        assert base64.b64decode(loaded.base64_data) == payload

    def test_loaded_pages_keep_page_order(self) -> None:
        fs = _store({2: b"two", 1: b"one", 3: b"three"})
        loaded = load_page_images(fs, _DIR)
        assert [p.page_number for p in loaded] == [1, 2, 3]
        assert base64.b64decode(loaded[0].base64_data) == b"one"


class TestVisionMessageContent:
    def test_prompt_first_then_labelled_pages(self) -> None:
        pages = [
            LoadedPageImage(page_number=1, path="p1", base64_data="QQ=="),
            LoadedPageImage(page_number=2, path="p2", base64_data="Qg=="),
        ]
        content = build_vision_message_content(pages, "What is the total?")
        assert content[0] == {"type": "text", "text": "What is the total?"}
        # "Page N" label immediately precedes each image, in page order.
        assert content[1] == {"type": "text", "text": "Page 1"}
        assert content[2]["type"] == "image_url"
        assert content[2]["image_url"]["url"] == "data:image/png;base64,QQ=="
        assert content[3] == {"type": "text", "text": "Page 2"}
        assert content[4]["image_url"]["url"] == "data:image/png;base64,Qg=="
        assert len(content) == 5

    def test_no_pages_yields_prompt_only(self) -> None:
        assert build_vision_message_content([], "q") == [{"type": "text", "text": "q"}]


class TestLocalFileStorageBackend:
    """UNS-809: the loader behaves identically on a real FileStorage backend."""

    def _local_fs(self) -> FileStorage:
        return FileStorage(provider=FileStorageProvider.LOCAL)

    def test_discovery_and_load_on_local_backend(self, tmp_path: Path) -> None:
        fs = self._local_fs()
        pages_dir = str(tmp_path / "doc" / "pages")
        fs.mkdir(pages_dir)
        payloads = {1: b"one", 2: b"two", 10: b"ten"}
        for n in range(1, 11):
            fs.write(
                path=f"{pages_dir}/page_{n:03d}.png",
                mode="wb",
                data=payloads.get(n, b"x"),
            )
        loaded = load_page_images(fs, pages_dir, page_cap=None)
        assert [p.page_number for p in loaded] == list(range(1, 11))
        assert base64.b64decode(loaded[9].base64_data) == b"ten"

    def test_missing_dir_on_local_backend(self, tmp_path: Path) -> None:
        with pytest.raises(PageImagesNotFoundError):
            discover_page_images(self._local_fs(), str(tmp_path / "absent" / "pages"))

    def test_partial_set_on_local_backend(self, tmp_path: Path) -> None:
        fs = self._local_fs()
        pages_dir = str(tmp_path / "doc" / "pages")
        fs.mkdir(pages_dir)
        for n in (1, 3):
            fs.write(path=f"{pages_dir}/page_{n:03d}.png", mode="wb", data=b"x")
        with pytest.raises(PageImageSetIncompleteError) as excinfo:
            discover_page_images(fs, pages_dir)
        assert excinfo.value.missing_pages == [2]


class TestStaleListingAndToctou:
    """Regressions from live testing.

    Object-store listing caches and read-time disappearance must surface
    typed errors, never raw IO errors.
    """

    def test_read_time_file_not_found_maps_to_incomplete(self) -> None:
        # Discovery sees 3 pages (e.g. a stale fsspec dircache), but page 2
        # was purged — the read must raise the typed incomplete-set error.
        fs = _store({1: b"a", 2: b"b", 3: b"c"})
        del fs._files[f"{_DIR}/page_002.png"]

        class StaleLsFs:
            def exists(self, path: str) -> bool:
                return True

            def ls(self, path: str) -> list[str]:
                return [f"{_DIR}/page_00{n}.png" for n in (1, 2, 3)]

            def read(self, path: str, mode: str = "rb", **_: object) -> bytes:
                return fs.read(path, mode)

        with pytest.raises(PageImageSetIncompleteError) as excinfo:
            load_page_images(StaleLsFs(), _DIR)
        err = excinfo.value
        assert err.missing_pages == [2]
        assert err.found_pages == [1, 3]
        assert "cache bypass" in str(err)

    def test_discovery_invalidates_backend_listing_cache(self) -> None:
        # When the FileStorage wraps an fsspec filesystem exposing
        # invalidate_cache (s3fs etc.), discovery must refresh it first.
        calls: list[str] = []

        class Underlying:
            def invalidate_cache(self, path: str) -> None:
                calls.append(path)

        fs = _store({1: b"a"})
        fs.fs = Underlying()
        discover_page_images(fs, _DIR)
        assert calls == [_DIR]

    def test_backends_without_listing_cache_are_fine(self) -> None:
        # The in-memory double has no .fs attribute — must not error.
        fs = _store({1: b"a"})
        assert [n for n, _ in discover_page_images(fs, _DIR)] == [1]


class TestByteBudget:
    """The page cap bounds count; the byte budget bounds payload size."""

    def test_over_budget_raises_typed_error(self) -> None:
        fs = _store({1: b"a" * 30, 2: b"b" * 30, 3: b"c" * 30})
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            load_page_images(fs, _DIR, max_total_bytes=50)
        err = excinfo.value
        # Bounded read: page 2 was read with length 21 (remaining + 1), so
        # the recorded total is budget + 1, and page 3 was never touched.
        assert err.total_bytes == 51
        assert err.max_total_bytes == 50
        assert "too large for image output mode" in str(err)

    def test_single_oversized_page_reads_are_bounded(self) -> None:
        # A single pathological object must never be fully allocated: each
        # read is capped at remaining-budget + 1 bytes regardless of the
        # object's real size (no size metadata needed).
        fs = _store({1: b"g" * (10 * 1024 * 1024)})  # 10MB object
        lengths: list[object] = []
        original_read = fs.read

        def recording_read(path: str, **kw: object) -> bytes | str:
            if not path.endswith(PAGE_LABELS_FILENAME):  # page images only
                lengths.append(kw.get("length"))
            return original_read(path, **kw)

        fs.read = recording_read
        with pytest.raises(PageImageSetTooLargeError):
            load_page_images(fs, _DIR, max_total_bytes=50)
        assert lengths == [51]  # only 51 bytes ever entered memory

    def test_budget_never_over_allocates_across_pages(self) -> None:
        # Aggregate guarantee: sum of bytes actually read stays <= budget+1.
        fs = _store({1: b"a" * 30, 2: b"b" * 30, 3: b"c" * 30})
        read_bytes: list[int] = []
        original_read = fs.read

        def recording_read(path: str, **kw: object) -> bytes | str:
            data = original_read(path, **kw)
            read_bytes.append(len(data))
            return data

        fs.read = recording_read
        with pytest.raises(PageImageSetTooLargeError):
            load_page_images(fs, _DIR, max_total_bytes=50)
        assert sum(read_bytes) <= 51

    def test_within_budget_loads(self) -> None:
        fs = _store({1: b"a" * 10, 2: b"b" * 10})
        assert len(load_page_images(fs, _DIR, max_total_bytes=25)) == 2

    def test_none_disables_budget(self) -> None:
        fs = _store({1: b"a" * 100})
        assert len(load_page_images(fs, _DIR, max_total_bytes=None)) == 1

    def test_default_budget_fits_the_strictest_provider_request_limit(
        self,
    ) -> None:
        # Bedrock and Gemini-inline both cap a request at 20MB; base64
        # inflates the payload ~33%, so the raw budget must leave room for
        # that. A budget above this lets the provider reject the request
        # before our own check fires.
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            DEFAULT_MAX_TOTAL_BYTES,
        )

        assert DEFAULT_MAX_TOTAL_BYTES == 14 * 1024 * 1024
        assert DEFAULT_MAX_TOTAL_BYTES * 4 / 3 < 20 * 1024 * 1024


class TestFixedPageCap:
    """The fixed cap: 90 pages / 14 MiB, tightened by the ceilings, never raised."""

    def test_absent_env_is_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PAGE_CAP_ENV, raising=False)
        monkeypatch.delenv(MAX_TOTAL_MB_ENV, raising=False)
        assert fixed_page_cap() == DEFAULT_PAGE_CAP
        assert fixed_max_total_bytes() == DEFAULT_MAX_TOTAL_BYTES

    def test_lower_ceiling_tightens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PAGE_CAP_ENV, "42")
        monkeypatch.setenv(MAX_TOTAL_MB_ENV, "6")
        assert fixed_page_cap() == 42
        assert fixed_max_total_bytes() == 6 * 1024 * 1024

    def test_higher_ceiling_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The env vars are ceilings: above the fixed cap they change nothing.
        monkeypatch.setenv(PAGE_CAP_ENV, "200")
        monkeypatch.setenv(MAX_TOTAL_MB_ENV, "50")
        assert fixed_page_cap() == DEFAULT_PAGE_CAP
        assert fixed_max_total_bytes() == DEFAULT_MAX_TOTAL_BYTES

    @pytest.mark.parametrize("raw", ["not-a-number", "0", "-5", "", "  "])
    def test_unusable_value_keeps_the_default(
        self, raw: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An operator typo must not fail extraction or remove the cap.
        monkeypatch.setenv(PAGE_CAP_ENV, raw)
        monkeypatch.setenv(MAX_TOTAL_MB_ENV, raw)
        assert fixed_page_cap() == DEFAULT_PAGE_CAP
        assert fixed_max_total_bytes() == DEFAULT_MAX_TOTAL_BYTES


class TestDeprecatedAccessorAliases:
    """The released cloud answer plugin imports configured_page_cap."""

    def test_aliases_return_the_fixed_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            configured_max_total_bytes,
            configured_page_cap,
        )

        for page, mib in (("40", "6"), ("200", "50"), ("", "")):
            monkeypatch.setenv(PAGE_CAP_ENV, page)
            monkeypatch.setenv(MAX_TOTAL_MB_ENV, mib)
            assert configured_page_cap() == fixed_page_cap()
            assert configured_max_total_bytes() == fixed_max_total_bytes()


class TestLoaderReadsConfiguredLimits:
    """Left unset, the loader's limits come from the env, not fixed defaults."""

    def test_default_page_cap_follows_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PAGE_CAP_ENV, "2")
        fs = _store({1: b"a", 2: b"b", 3: b"c"})
        with pytest.raises(PageCapExceededError):
            load_page_images(fs, _DIR)

    def test_explicit_none_still_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PAGE_CAP_ENV, "2")
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "1")
        fs = _store({1: b"a", 2: b"b", 3: b"c" * (2 * 1024 * 1024)})
        assert len(load_page_images(fs, _DIR, page_cap=None, max_total_bytes=None)) == 3

    def test_explicit_value_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PAGE_CAP_ENV, "2")
        fs = _store({1: b"a", 2: b"b", 3: b"c"})
        assert len(load_page_images(fs, _DIR, page_cap=3)) == 3


class TestByteBudgetMessage:
    def test_over_budget_message_is_user_facing(self) -> None:
        fs = _store({1: b"x" * 700_000, 2: b"y" * 700_000, 3: b"z"})
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            load_page_images(fs, _DIR, page_cap=None, max_total_bytes=1024 * 1024)
        msg = str(excinfo.value)
        assert msg.startswith("This document is too large for image output mode.")
        assert "go over the 1.0 MiB limit at page 2 of 3" in msg
        assert "Split the document into smaller files" in msg
        # Operator-only knob and the confusing phrasing are gone.
        assert "VLM_IMAGE_ANSWER_MAX_TOTAL_MB" not in msg
        assert "however many pages" not in msg


class TestCapMatchesBudget:
    """The page cap must stay within what the byte budget can deliver.

    The extraction-time pre-check only knows the page COUNT. If the cap
    allows more pages than the byte budget can carry, a document between the
    two passes the pre-check, is converted and billed per page, and then
    fails at answer time — billed for something that can never be answered.
    """

    # Lightest page render measured from LLMWhisperer at its default 150 DPI:
    # a 50-page PDF produced an 8,233,339-byte pdf-to-images archive.
    #
    # This is the ARCHIVE size, not the sum of extracted PNG bytes that
    # load_page_images counts — an approximation, and deliberately treated
    # as one. PNG data is already deflate-compressed, so zipping it saves
    # little, and per-entry headers are ~100 bytes; the archive should be
    # within a few percent of the image bytes, which is a couple of pages
    # either side at this cap. So the guard below allows that much slack
    # rather than asserting an exact page count it cannot back up. Measuring
    # extracted bytes on real documents is the proper calibration.
    _APPROX_LIGHT_PAGE_BYTES = 8_233_339 // 50  # ~164,666 bytes

    # Pages of slack for the archive-vs-extracted-bytes measurement error.
    _MEASUREMENT_SLACK_PAGES = 2

    def test_cap_stays_near_what_the_budget_can_carry(self) -> None:
        # At the lightest measured page size the 14MB budget holds ~89 pages;
        # 90 is the round product number at the top of that. This fails if
        # the cap and the budget drift apart by more than the measurement
        # slack — e.g. the cap raised back to 300, or the budget cut without
        # lowering the cap — which is the drift that reopens the
        # billed-then-rejected window.
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            DEFAULT_MAX_TOTAL_BYTES,
        )

        capacity = DEFAULT_MAX_TOTAL_BYTES // self._APPROX_LIGHT_PAGE_BYTES
        assert DEFAULT_PAGE_CAP <= capacity + self._MEASUREMENT_SLACK_PAGES


class TestModelAwareLimits:
    """``limits=`` replaces the fixed cap/budget with the model's policy."""

    @staticmethod
    def _policy(**values: int | None) -> "ImageModePolicy":
        import dataclasses

        from unstract.sdk1.utils.image_limits import ImageModePolicy, resolve_image_limits

        limits = resolve_image_limits(
            "bedrock", "bedrock/anthropic.claude-sonnet-4-5-v1:0"
        )
        for name, value in values.items():
            limits = dataclasses.replace(
                limits, **{name: dataclasses.replace(getattr(limits, name), value=value)}
            )
        return ImageModePolicy.from_limits([limits])

    def test_page_cap_from_policy_before_any_read(self) -> None:
        fs = _store({n: minimal_png() for n in range(1, 22)})
        reads: list[str] = []
        original_read = fs.read

        def recording_read(path: str, **kw: object) -> bytes | str:
            if not path.endswith(PAGE_LABELS_FILENAME):  # page images only
                reads.append(path)
            return original_read(path, **kw)

        fs.read = recording_read
        with pytest.raises(PageCapExceededError) as excinfo:
            load_page_images(fs, _DIR, limits=self._policy())
        assert excinfo.value.page_cap == 20
        assert "Amazon Bedrock" in str(excinfo.value)
        assert reads == []

    def test_byte_budget_from_policy_is_derived_from_the_wire_limit(self) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            PageImageSetTooLargeError,
        )

        policy = self._policy(max_request_bytes=1_000_000)
        fs = _store({1: b"a" * 500_000, 2: b"b" * 500_000})
        lengths: list[object] = []
        original_read = fs.read

        def recording_read(path: str, **kw: object) -> bytes | str:
            if not path.endswith(PAGE_LABELS_FILENAME):  # page images only
                lengths.append(kw.get("length"))
            return original_read(path, **kw)

        fs.read = recording_read
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            load_page_images(fs, _DIR, limits=policy, prompt_text_bytes=100)
        budget = policy.raw_byte_budget(page_count=2, prompt_text_bytes=100)
        assert excinfo.value.max_total_bytes == budget
        # Bounded reads are sized from the derived budget.
        assert lengths[0] == budget + 1
        assert "once encoded" in str(excinfo.value)

    def test_per_image_limit_from_policy(self) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import PageImageTooLargeError

        fs = _store({1: b"a" * 10, 2: b"b" * 500})
        with pytest.raises(PageImageTooLargeError) as excinfo:
            load_page_images(fs, _DIR, limits=self._policy(max_image_bytes=100))
        assert excinfo.value.page_number == 2

    def test_per_image_error_names_the_document_page(self) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import PageImageTooLargeError

        fs = _store(
            {1: b"a" * 10, 2: b"b" * 500}, extra={"pages.json": b'{"pages": [10, 12]}'}
        )
        with pytest.raises(PageImageTooLargeError) as excinfo:
            load_page_images(fs, _DIR, limits=self._policy(max_image_bytes=100))
        assert str(excinfo.value).startswith("Page 12 of this document is")

    def test_within_policy_loads(self) -> None:
        fs = _store({1: minimal_png(), 2: minimal_png()})
        assert len(load_page_images(fs, _DIR, limits=self._policy())) == 2

    def test_policy_and_legacy_kwargs_are_mutually_exclusive(self) -> None:
        fs = _store({1: minimal_png()})
        with pytest.raises(ValueError):
            load_page_images(fs, _DIR, limits=self._policy(), page_cap=5)

    def test_ceiling_only_policy_applies_operator_ceilings(self) -> None:
        from unstract.sdk1.utils.image_limits import ImageModePolicy

        fs = _store({n: minimal_png() for n in range(1, 4)})
        policy = ImageModePolicy.ceiling_only(page_ceiling=2)
        with pytest.raises(PageCapExceededError):
            load_page_images(fs, _DIR, limits=policy)


class TestConfiguredCeilings:
    """The env vars read as optional ceilings (no value -> no ceiling)."""

    def test_absent_env_is_no_ceiling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            MAX_TOTAL_MB_ENV,
            configured_page_ceiling,
            configured_request_bytes_ceiling,
        )

        monkeypatch.delenv(PAGE_CAP_ENV, raising=False)
        monkeypatch.delenv(MAX_TOTAL_MB_ENV, raising=False)
        assert configured_page_ceiling() is None
        assert configured_request_bytes_ceiling() is None

    def test_env_values_are_ceilings_in_the_legacy_units(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            MAX_TOTAL_MB_ENV,
            configured_page_ceiling,
            configured_request_bytes_ceiling,
        )

        monkeypatch.setenv(PAGE_CAP_ENV, "40")
        monkeypatch.setenv(MAX_TOTAL_MB_ENV, "3")
        assert configured_page_ceiling() == 40
        assert configured_request_bytes_ceiling() == 3 * 1024 * 1024

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_empty_value_is_unset(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        raw: str,
    ) -> None:
        # A chart that renders VAR: "" means "not set", not an invalid value.
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            MAX_TOTAL_MB_ENV,
            configured_page_ceiling,
            configured_request_bytes_ceiling,
        )

        monkeypatch.setenv(PAGE_CAP_ENV, raw)
        monkeypatch.setenv(MAX_TOTAL_MB_ENV, raw)
        with caplog.at_level("WARNING"):
            assert configured_page_ceiling() is None
            assert configured_request_bytes_ceiling() is None
            assert fixed_page_cap() == DEFAULT_PAGE_CAP
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_a_bad_value_is_logged_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            configured_page_ceiling,
        )

        monkeypatch.setenv(PAGE_CAP_ENV, "lots")
        with caplog.at_level("ERROR"):
            for _ in range(3):
                assert configured_page_ceiling() == DEFAULT_PAGE_CAP
        assert len([r for r in caplog.records if r.levelname == "ERROR"]) == 1

    @pytest.mark.parametrize("raw", ["lots", "10MB", "0", "-5"])
    def test_unusable_value_keeps_the_fixed_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        raw: str,
    ) -> None:
        # An operator typo must never remove the ceiling (unbounded reads
        # into worker memory, a 999-page bound); it keeps 90 pages / 14 MiB.
        from unstract.sdk1.adapters.x2text.page_image_loader import (
            DEFAULT_MAX_TOTAL_BYTES,
            MAX_TOTAL_MB_ENV,
            configured_page_ceiling,
            configured_request_bytes_ceiling,
        )

        monkeypatch.setenv(PAGE_CAP_ENV, raw)
        monkeypatch.setenv(MAX_TOTAL_MB_ENV, raw)
        with caplog.at_level("ERROR"):
            assert configured_page_ceiling() == DEFAULT_PAGE_CAP
            assert configured_request_bytes_ceiling() == DEFAULT_MAX_TOTAL_BYTES
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert {PAGE_CAP_ENV, MAX_TOTAL_MB_ENV} <= {
            name
            for r in errors
            for name in (PAGE_CAP_ENV, MAX_TOTAL_MB_ENV)
            if name in r.getMessage()
        }


class TestDocumentPageLabels:
    """pages.json gives each image its document page for the label only."""

    def _labels(self, fs: InMemoryFileStorage) -> list[str]:
        content = build_vision_message_content(load_page_images(fs, _DIR), "Q")
        return [block["text"] for block in content[1:] if block["type"] == "text"]

    def test_labels_use_document_pages(self) -> None:
        fs = _store({1: b"a", 2: b"b"}, extra={"pages.json": b'{"pages": [10, 12]}'})
        loaded = load_page_images(fs, _DIR)
        assert [p.page_number for p in loaded] == [1, 2]
        assert [p.document_page for p in loaded] == [10, 12]
        assert self._labels(fs) == ["Page 10", "Page 12"]

    def test_absent_file_falls_back_to_file_numbers(self) -> None:
        fs = _store({1: b"a", 2: b"b"})
        assert self._labels(fs) == ["Page 1", "Page 2"]

    @pytest.mark.parametrize(
        "raw",
        [
            b"not json",
            b"[10, 12]",
            b'{"pages": [10]}',
            b'{"pages": [12, 10]}',
            b'{"pages": [10, 10]}',
            b'{"pages": [0, 12]}',
            b'{"pages": ["10", 12]}',
            b'{"pages": [true, 12]}',
        ],
        ids=[
            "garbage",
            "bare-list",
            "short",
            "unordered",
            "dupes",
            "zero",
            "str",
            "bool",
        ],
    )
    def test_invalid_file_falls_back_to_file_numbers(
        self, raw: bytes, caplog: pytest.LogCaptureFixture
    ) -> None:
        fs = _store({1: b"a", 2: b"b"}, extra={"pages.json": raw})
        assert self._labels(fs) == ["Page 1", "Page 2"]
        # The extraction wrote it for a selection: the labels are now wrong.
        assert any(
            r.levelname == "ERROR" and PAGE_LABELS_FILENAME in r.getMessage()
            for r in caplog.records
        )

    def test_unreadable_file_is_logged_at_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        fs = _store({1: b"a"}, extra={"pages.json": b'{"pages": [3]}'})
        original_read = fs.read

        def read(path: str, **kw: object) -> bytes:
            if path.endswith(PAGE_LABELS_FILENAME):
                raise OSError("connection reset")
            return original_read(path, **kw)

        fs.read = read
        assert self._labels(fs) == ["Page 1"]
        assert any(
            r.levelname == "ERROR" and "connection reset" in r.getMessage()
            for r in caplog.records
        )

    def test_labels_file_is_not_a_page(self) -> None:
        fs = _store({1: b"a"}, extra={"pages.json": b'{"pages": [3]}'})
        assert [n for n, _ in discover_page_images(fs, _DIR)] == [1]


class TestDocumentPageInLoaderMessages:
    def test_byte_budget_message_names_the_document_page(self) -> None:
        fs = _store(
            {1: b"a" * 40, 2: b"b" * 40}, extra={"pages.json": b'{"pages": [10, 12]}'}
        )
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            load_page_images(fs, _DIR, max_total_bytes=50)
        assert "limit at page 12 (image 2 of 2)" in str(excinfo.value)

    def test_byte_budget_message_falls_back_to_the_position(self) -> None:
        fs = _store({1: b"a" * 40, 2: b"b" * 40})
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            load_page_images(fs, _DIR, max_total_bytes=50)
        assert "limit at page 2 of 2" in str(excinfo.value)

    def test_fixed_cap_message_names_a_selection(self) -> None:
        fs = _store(
            {1: b"a", 2: b"b", 3: b"c"}, extra={"pages.json": b'{"pages": [4, 8, 9]}'}
        )
        with pytest.raises(PageCapExceededError) as excinfo:
            load_page_images(fs, _DIR, page_cap=2)
        msg = str(excinfo.value)
        assert "'Pages to extract' selects 3 pages, and the limit is 2" in msg
        assert "This document has" not in msg

    def test_fixed_cap_message_without_a_selection_is_unchanged(self) -> None:
        fs = _store({1: b"a", 2: b"b", 3: b"c"})
        with pytest.raises(PageCapExceededError) as excinfo:
            load_page_images(fs, _DIR, page_cap=2)
        assert "This document has too many pages" in str(excinfo.value)
        assert "It has 3 pages, and the limit is 2" in str(excinfo.value)

    def test_missing_labels_file_is_never_probed(self) -> None:
        # The listing shows no pages.json, so it is neither checked nor read
        # (a read of a missing object costs failed GETs and a cache flush).
        fs = _store({1: b"a"})
        original_exists, original_read = fs.exists, fs.read
        reads: list[str] = []

        def exists(path: str) -> bool:
            assert not path.endswith(PAGE_LABELS_FILENAME), "labels: not probed"
            return original_exists(path)

        fs.exists = exists
        fs.read = lambda path, **kw: reads.append(path) or original_read(path, **kw)
        assert [p.page_number for p in load_page_images(fs, _DIR)] == [1]
        assert not [p for p in reads if p.endswith(PAGE_LABELS_FILENAME)]

    def test_listed_labels_file_is_read_once(self) -> None:
        fs = _store({1: b"a", 2: b"b"}, extra={"pages.json": b'{"pages": [10, 12]}'})
        original_read = fs.read
        reads: list[str] = []
        fs.read = lambda path, **kw: reads.append(path) or original_read(path, **kw)
        load_page_images(fs, _DIR)
        assert [p for p in reads if p.endswith(PAGE_LABELS_FILENAME)] == [
            f"{_DIR}/{PAGE_LABELS_FILENAME}"
        ]

    def test_labels_removed_after_the_listing_fall_back_quietly(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        fs = _store({1: b"a"}, extra={"pages.json": b'{"pages": [3]}'})
        original_read = fs.read

        def read(path: str, **kw: object) -> bytes:
            if path.endswith(PAGE_LABELS_FILENAME):
                raise FileNotFoundError(path)
            return original_read(path, **kw)

        fs.read = read
        loaded = load_page_images(fs, _DIR)
        assert [p.document_page for p in loaded] == [None]
        assert not [r for r in caplog.records if r.levelname == "ERROR"]
