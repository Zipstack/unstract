"""In-memory PDF page rasteriser for VLM vision calls.

Renders PDF pages to preprocessed PNG bytes without writing to disk.
Preprocessing mirrors the agentic table pipeline:
    1. Render at DPI via pypdfium2
    2. Upscale 2x with LANCZOS
    3. Gaussian blur (radius=0.5) to smooth aliasing
    4. UnsharpMask to restore text sharpness
    5. Constrain to max_dimension
"""

import io
import logging
import os
from dataclasses import dataclass

import pypdfium2 as pdfium
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

MAX_VISION_PAGES = int(os.environ.get("MAX_VISION_PAGES", "10"))


@dataclass
class RenderSettings:
    """Configuration for PDF page rendering and preprocessing."""

    dpi: int = 150
    max_dimension: int = 1568

    @property
    def scale(self) -> float:
        """Convert DPI to pypdfium2 scale factor (PDF points are 72 DPI)."""
        return self.dpi / 72.0


def _preprocess_image(img: Image.Image, max_dimension: int) -> Image.Image:
    """Apply the proven agentic-table preprocessing pipeline.

    Args:
        img: Raw rendered PIL image (RGB).
        max_dimension: Maximum width or height after preprocessing.

    Returns:
        Preprocessed PIL image ready for PNG encoding.
    """
    # Upscale 2x with high-quality resampling
    upscaled = img.resize(
        (img.width * 2, img.height * 2),
        Image.Resampling.LANCZOS,
    )

    # Smooth aliasing artifacts
    smoothed = upscaled.filter(ImageFilter.GaussianBlur(radius=0.5))

    # Restore text sharpness
    sharpened = smoothed.filter(
        ImageFilter.UnsharpMask(radius=1, percent=50, threshold=3)
    )

    # Constrain to max_dimension
    if max(sharpened.size) > max_dimension:
        ratio = max_dimension / max(sharpened.size)
        new_size = (int(sharpened.width * ratio), int(sharpened.height * ratio))
        sharpened = sharpened.resize(new_size, Image.Resampling.LANCZOS)

    return sharpened


def rasterise_pages(
    file_bytes: bytes,
    settings: RenderSettings | None = None,
    page_set: set[int] | None = None,
    max_pages: int = MAX_VISION_PAGES,
) -> list[tuple[int, bytes]]:
    """Render PDF pages to preprocessed PNG bytes in memory.

    Args:
        file_bytes: Raw PDF file content.
        settings: Render configuration. Uses defaults if None.
        page_set: 0-indexed page numbers to render. None renders all pages.
        max_pages: Maximum number of pages to render. Logs a warning
            if the document has more pages than this limit.

    Returns:
        List of (page_number, png_bytes) tuples. Page numbers are 0-indexed.

    Raises:
        ValueError: If file_bytes is empty or not a valid PDF.
    """
    if not file_bytes:
        raise ValueError("file_bytes is empty")

    if settings is None:
        settings = RenderSettings()

    pdf = pdfium.PdfDocument(file_bytes)
    try:
        total_pages = len(pdf)
        if total_pages == 0:
            logger.warning("PDF has 0 pages, nothing to rasterise")
            return []

        # Determine which pages to render
        if page_set is not None:
            # Filter to valid pages and sort
            pages_to_render = sorted(p for p in page_set if 0 <= p < total_pages)
            invalid = page_set - set(range(total_pages))
            if invalid:
                logger.warning(
                    "Skipping invalid page numbers %s (PDF has %d pages)",
                    sorted(invalid),
                    total_pages,
                )
        else:
            pages_to_render = list(range(total_pages))

        # Apply max_pages cap
        if len(pages_to_render) > max_pages:
            logger.warning(
                "Truncating from %d to %d pages (MAX_VISION_PAGES=%d)",
                len(pages_to_render),
                max_pages,
                max_pages,
            )
            pages_to_render = pages_to_render[:max_pages]

        results: list[tuple[int, bytes]] = []
        for page_num in pages_to_render:
            page = pdf[page_num]
            bitmap = page.render(scale=settings.scale)
            pil_image = bitmap.to_pil()

            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            # Apply preprocessing pipeline
            processed = _preprocess_image(pil_image, settings.max_dimension)

            # Encode as PNG bytes
            buffer = io.BytesIO()
            processed.save(buffer, format="PNG", optimize=True)
            results.append((page_num, buffer.getvalue()))

            logger.debug(
                "Rasterised page %d: %dx%d → %dx%d",
                page_num,
                pil_image.width,
                pil_image.height,
                processed.width,
                processed.height,
            )

        logger.info(
            "Rasterised %d/%d pages (dpi=%d, max_dim=%d)",
            len(results),
            total_pages,
            settings.dpi,
            settings.max_dimension,
        )
        return results
    finally:
        pdf.close()
