"""Tests for the PDF rasteriser module."""

import io
from typing import Self
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from unstract.sdk1.rasteriser import (
    RenderSettings,
    _preprocess_image,
    rasterise_pages,
)


def _make_pil_image(
    width: int = 100,
    height: int = 100,
    mode: str = "RGB",
) -> Image.Image:
    """Create a simple test PIL image."""
    return Image.new(mode, (width, height), color="red")


# ---------------------------------------------------------------------------
# RenderSettings
# ---------------------------------------------------------------------------


class TestRenderSettings:
    """Tests for the RenderSettings dataclass."""

    def test_defaults(self: Self) -> None:
        """Default DPI=150, max_dimension=1568."""
        s = RenderSettings()
        assert s.dpi == 150
        assert s.max_dimension == 1568

    def test_scale_at_72_dpi(self: Self) -> None:
        """At 72 DPI, scale should be 1.0."""
        assert RenderSettings(dpi=72).scale == pytest.approx(1.0)

    def test_scale_at_150_dpi(self: Self) -> None:
        """At 150 DPI, scale should be 150/72."""
        assert RenderSettings(dpi=150).scale == pytest.approx(150.0 / 72.0)

    def test_custom_values(self: Self) -> None:
        """Custom values should be stored correctly."""
        s = RenderSettings(dpi=300, max_dimension=2048)
        assert s.dpi == 300
        assert s.max_dimension == 2048


# ---------------------------------------------------------------------------
# _preprocess_image
# ---------------------------------------------------------------------------


class TestPreprocessImage:
    """Tests for _preprocess_image() preprocessing pipeline."""

    def test_small_image_upscaled_2x(self: Self) -> None:
        """Small images should be upscaled 2x (under max_dimension)."""
        img = _make_pil_image(100, 100)
        result = _preprocess_image(img, max_dimension=1568)
        # 100 -> 200 (2x upscale), stays under 1568
        assert result.width == 200
        assert result.height == 200

    def test_large_image_constrained(self: Self) -> None:
        """After 2x upscale, images exceeding max_dimension get constrained."""
        img = _make_pil_image(1000, 800)
        result = _preprocess_image(img, max_dimension=500)
        # 1000 -> 2000 (2x), then constrained to 500 max dim
        assert max(result.size) <= 500

    def test_preserves_rgb_mode(self: Self) -> None:
        """Output should always be RGB."""
        img = _make_pil_image(50, 50)
        result = _preprocess_image(img, max_dimension=1568)
        assert result.mode == "RGB"

    def test_aspect_ratio_preserved(self: Self) -> None:
        """Constraining should preserve the aspect ratio."""
        img = _make_pil_image(800, 400)  # 2:1 ratio
        result = _preprocess_image(img, max_dimension=500)
        ratio_input = 800 / 400
        ratio_output = result.width / result.height
        assert ratio_input == pytest.approx(ratio_output, abs=0.15)


# ---------------------------------------------------------------------------
# rasterise_pages — mocked pypdfium2
# ---------------------------------------------------------------------------


def _make_mock_pdf(
    num_pages: int = 1,
    img_size: tuple[int, int] = (200, 200),
) -> MagicMock:
    """Create a mock PdfDocument."""
    mock_doc = MagicMock()
    mock_doc.__len__ = MagicMock(return_value=num_pages)

    def _getitem(idx: int) -> MagicMock:
        mock_page = MagicMock()
        mock_bitmap = MagicMock()
        mock_bitmap.to_pil.return_value = _make_pil_image(*img_size)
        mock_page.render.return_value = mock_bitmap
        return mock_page

    mock_doc.__getitem__ = MagicMock(side_effect=_getitem)
    return mock_doc


class TestRasterisePages:
    """Tests for rasterise_pages() with mocked pypdfium2."""

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_single_page(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """Should produce one (page_num, png_bytes) tuple for a 1-page PDF."""
        mock_pdf_cls.return_value = _make_mock_pdf(1)

        results = rasterise_pages(b"fake-pdf-bytes")

        assert len(results) == 1
        page_num, png_bytes = results[0]
        assert page_num == 0
        assert len(png_bytes) > 0

        # Verify output is valid PNG
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_multi_page(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """Should rasterise all pages of a multi-page PDF."""
        mock_pdf_cls.return_value = _make_mock_pdf(3)

        results = rasterise_pages(b"fake-pdf")

        assert len(results) == 3
        assert [r[0] for r in results] == [0, 1, 2]

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_page_set_filtering(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """Should only render pages in page_set."""
        mock_pdf_cls.return_value = _make_mock_pdf(5)

        results = rasterise_pages(b"fake-pdf", page_set={1, 3})

        assert len(results) == 2
        assert [r[0] for r in results] == [1, 3]

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_page_set_skips_invalid(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """Should skip page numbers beyond the PDF's page count."""
        mock_pdf_cls.return_value = _make_mock_pdf(3)

        results = rasterise_pages(b"fake-pdf", page_set={0, 1, 10, 20})

        assert len(results) == 2
        assert [r[0] for r in results] == [0, 1]

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_max_pages_truncation(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """Should cap at max_pages."""
        mock_pdf_cls.return_value = _make_mock_pdf(20)

        results = rasterise_pages(b"fake-pdf", max_pages=5)

        assert len(results) == 5
        assert [r[0] for r in results] == [0, 1, 2, 3, 4]

    def test_empty_bytes_raises_value_error(self: Self) -> None:
        """Empty file_bytes should raise ValueError."""
        with pytest.raises(ValueError, match="file_bytes is empty"):
            rasterise_pages(b"")

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_zero_page_pdf_returns_empty(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """PDF with 0 pages should return empty list."""
        mock_pdf_cls.return_value = _make_mock_pdf(0)

        results = rasterise_pages(b"fake-pdf")

        assert results == []

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_rgba_converted_to_rgb(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """RGBA images from the renderer should be converted to RGB."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_page = MagicMock()
        mock_bitmap = MagicMock()
        # Return an RGBA image
        mock_bitmap.to_pil.return_value = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        mock_page.render.return_value = mock_bitmap
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_pdf_cls.return_value = mock_doc

        results = rasterise_pages(b"fake-pdf")

        assert len(results) == 1
        output_img = Image.open(io.BytesIO(results[0][1]))
        assert output_img.mode == "RGB"

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_pdf_closed_after_processing(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """PDF document should be closed after successful processing."""
        mock_doc = _make_mock_pdf(1)
        mock_pdf_cls.return_value = mock_doc

        rasterise_pages(b"fake-pdf")

        mock_doc.close.assert_called_once()

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_pdf_closed_on_error(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """PDF document should be closed even when an error occurs."""
        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(side_effect=RuntimeError("bad pdf"))
        mock_pdf_cls.return_value = mock_doc

        with pytest.raises(RuntimeError, match="bad pdf"):
            rasterise_pages(b"fake-pdf")

        mock_doc.close.assert_called_once()

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_default_settings_when_none(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """When settings=None, default RenderSettings should be used."""
        mock_pdf_cls.return_value = _make_mock_pdf(1)

        # Should not raise
        results = rasterise_pages(b"fake-pdf", settings=None)

        assert len(results) == 1

    @patch("unstract.sdk1.rasteriser.pdfium.PdfDocument")
    def test_page_set_sorted_output(
        self: Self,
        mock_pdf_cls: MagicMock,
    ) -> None:
        """Pages should be rendered in sorted order."""
        mock_pdf_cls.return_value = _make_mock_pdf(10)

        results = rasterise_pages(b"fake-pdf", page_set={5, 2, 8, 0})

        page_nums = [r[0] for r in results]
        assert page_nums == [0, 2, 5, 8]
