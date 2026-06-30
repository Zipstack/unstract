"""Vision message builder for VLM completions.

Assembles OpenAI-style messages with text + base64 image blocks.
LiteLLM auto-translates for Anthropic, Bedrock, Vertex, etc.
"""

import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_vision_messages(
    system_prompt: str,
    text_context: str | None,
    page_images: list[tuple[int, bytes]],
    prompt: str,
    mode: str,
) -> list[dict[str, Any]]:
    """Assemble OpenAI-style multimodal messages for VLM completion.

    The ordering of text and image content blocks depends on the mode:

    - ``spatial_helper``: Text context first (primary source of truth),
      then images as spatial aids for layout understanding.
    - ``source_of_truth``: Images first (primary source of truth),
      then text as an optional secondary hint.

    Args:
        system_prompt: System message content for the LLM.
        text_context: Extracted text from the document. May be None or
            empty for image-only extraction.
        page_images: List of (page_number, png_bytes) from the rasteriser.
        prompt: The user's extraction prompt / question.
        mode: Vision mode — ``"spatial_helper"`` or ``"source_of_truth"``.

    Returns:
        List of message dicts ready for ``llm.complete_vision()``.

    Raises:
        ValueError: If mode is not one of the supported values.
    """
    valid_modes = ("spatial_helper", "source_of_truth")
    if mode not in valid_modes:
        raise ValueError(f"Invalid vision mode '{mode}'. Must be one of {valid_modes}")

    if not page_images:
        raise ValueError("page_images is empty — cannot build vision messages")

    messages: list[dict[str, Any]] = []

    # System message
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Build multimodal user content blocks
    content: list[dict[str, Any]] = []

    if mode == "spatial_helper":
        # Text is primary, images are spatial aids
        _append_text_context(content, text_context, is_primary=True)
        _append_image_blocks(content, page_images, is_primary=False)
    else:
        # source_of_truth: Images are primary, text is a hint
        _append_image_blocks(content, page_images, is_primary=True)
        _append_text_context(content, text_context, is_primary=False)

    # Append the extraction prompt last
    content.append({"type": "text", "text": prompt})

    messages.append({"role": "user", "content": content})

    logger.debug(
        "Built vision messages: mode=%s, images=%d, has_text=%s",
        mode,
        len(page_images),
        bool(text_context),
    )
    return messages


def _append_text_context(
    content: list[dict[str, Any]],
    text_context: str | None,
    is_primary: bool,
) -> None:
    """Append text context block with appropriate framing."""
    if not text_context:
        if is_primary:
            # This shouldn't happen for spatial_helper — text is expected
            logger.warning("No text context available for primary text source")
        return

    if is_primary:
        label = "DOCUMENT TEXT (primary source — use for extraction):"
    else:
        label = "DOCUMENT TEXT (supplementary reference):"

    content.append({"type": "text", "text": f"{label}\n{text_context}"})


def _append_image_blocks(
    content: list[dict[str, Any]],
    page_images: list[tuple[int, bytes]],
    is_primary: bool,
) -> None:
    """Append image blocks with page labels."""
    if is_primary:
        label = "DOCUMENT PAGES (primary source — use for extraction):"
    else:
        label = "DOCUMENT PAGES (spatial reference for layout context):"

    content.append({"type": "text", "text": label})

    for page_num, png_bytes in page_images:
        b64 = base64.standard_b64encode(png_bytes).decode("utf-8")
        content.append({"type": "text", "text": f"Page {page_num + 1}:"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }
        )
