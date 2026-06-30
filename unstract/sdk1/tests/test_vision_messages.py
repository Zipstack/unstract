"""Tests for vision message builder (build_vision_messages)."""

import base64
from typing import Self

import pytest
from unstract.sdk1.vision import build_vision_messages


@pytest.fixture()
def sample_images() -> list[tuple[int, bytes]]:
    """Create sample page images for testing."""
    return [
        (0, b"fake-png-page-0"),
        (1, b"fake-png-page-1"),
    ]


class TestBuildVisionMessages:
    """Tests for build_vision_messages()."""

    def test_spatial_helper_text_before_images(
        self: Self,
        sample_images: list[tuple[int, bytes]],
    ) -> None:
        """In spatial_helper mode, text context appears before images."""
        messages = build_vision_messages(
            system_prompt="Be helpful",
            text_context="Document text here",
            page_images=sample_images,
            prompt="Extract the value",
            mode="spatial_helper",
        )

        # System message first
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Be helpful"

        # User message with content blocks
        user_msg = messages[1]
        assert user_msg["role"] == "user"
        content = user_msg["content"]

        # First content block: text (primary)
        assert content[0]["type"] == "text"
        assert "primary source" in content[0]["text"]
        assert "Document text here" in content[0]["text"]

        # Images come after text
        image_blocks = [
            b for b in content if b.get("type") == "image_url"
        ]
        assert len(image_blocks) == 2

        # Last block is the extraction prompt
        assert content[-1]["type"] == "text"
        assert content[-1]["text"] == "Extract the value"

    def test_source_of_truth_images_before_text(
        self: Self,
        sample_images: list[tuple[int, bytes]],
    ) -> None:
        """In source_of_truth mode, images appear before text context."""
        messages = build_vision_messages(
            system_prompt="Be helpful",
            text_context="Document text",
            page_images=sample_images,
            prompt="Extract",
            mode="source_of_truth",
        )

        user_content = messages[1]["content"]

        # First content block: images (primary)
        assert user_content[0]["type"] == "text"
        assert "primary source" in user_content[0]["text"]
        assert "PAGES" in user_content[0]["text"]

        # Text comes after images — find supplementary text
        text_blocks = [
            b
            for b in user_content
            if b.get("type") == "text"
            and "supplementary" in b.get("text", "")
        ]
        assert len(text_blocks) == 1
        assert "Document text" in text_blocks[0]["text"]

    def test_images_encoded_as_base64(self: Self) -> None:
        """Image bytes should be base64-encoded in data: URLs."""
        page_images = [(0, b"test-png-bytes")]
        messages = build_vision_messages(
            system_prompt="",
            text_context="text",
            page_images=page_images,
            prompt="Extract",
            mode="spatial_helper",
        )

        # No system prompt -> user message is messages[0]
        user_content = messages[0]["content"]
        image_blocks = [
            b for b in user_content if b.get("type") == "image_url"
        ]
        assert len(image_blocks) == 1

        url = image_blocks[0]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")

        # Verify round-trip decoding
        b64_part = url.split(",", 1)[1]
        assert base64.standard_b64decode(b64_part) == b"test-png-bytes"

    def test_page_numbers_1_indexed_in_labels(self: Self) -> None:
        """Each image should have a 'Page N:' label (1-indexed)."""
        page_images = [(0, b"p0"), (3, b"p3")]
        messages = build_vision_messages(
            system_prompt="sys",
            text_context="txt",
            page_images=page_images,
            prompt="prompt",
            mode="spatial_helper",
        )

        user_content = messages[1]["content"]
        text_values = [
            b["text"]
            for b in user_content
            if b.get("type") == "text"
        ]

        # Page labels are 1-indexed (page_num + 1)
        assert any("Page 1:" in t for t in text_values)
        assert any("Page 4:" in t for t in text_values)

    def test_empty_system_prompt_omitted(
        self: Self,
        sample_images: list[tuple[int, bytes]],
    ) -> None:
        """Empty system prompt should not produce a system message."""
        messages = build_vision_messages(
            system_prompt="",
            text_context="text",
            page_images=sample_images,
            prompt="Extract",
            mode="spatial_helper",
        )

        # No system message, just user message
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_none_text_context_spatial_helper(
        self: Self,
        sample_images: list[tuple[int, bytes]],
    ) -> None:
        """None text_context in spatial_helper should omit text block."""
        messages = build_vision_messages(
            system_prompt="sys",
            text_context=None,
            page_images=sample_images,
            prompt="Extract",
            mode="spatial_helper",
        )

        user_content = messages[1]["content"]
        doc_text_blocks = [
            b
            for b in user_content
            if b.get("type") == "text"
            and "DOCUMENT TEXT" in b.get("text", "")
        ]
        assert len(doc_text_blocks) == 0

    def test_none_text_context_source_of_truth(
        self: Self,
        sample_images: list[tuple[int, bytes]],
    ) -> None:
        """None text_context in source_of_truth is normal (image-only)."""
        messages = build_vision_messages(
            system_prompt="sys",
            text_context=None,
            page_images=sample_images,
            prompt="Extract",
            mode="source_of_truth",
        )

        user_content = messages[1]["content"]
        doc_text_blocks = [
            b
            for b in user_content
            if b.get("type") == "text"
            and "DOCUMENT TEXT" in b.get("text", "")
        ]
        assert len(doc_text_blocks) == 0

    def test_invalid_mode_raises_value_error(
        self: Self,
        sample_images: list[tuple[int, bytes]],
    ) -> None:
        """Invalid mode should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid vision mode"):
            build_vision_messages(
                system_prompt="sys",
                text_context="text",
                page_images=sample_images,
                prompt="Extract",
                mode="invalid_mode",
            )

    def test_empty_page_images_raises_value_error(self: Self) -> None:
        """Empty page_images should raise ValueError."""
        with pytest.raises(ValueError, match="page_images is empty"):
            build_vision_messages(
                system_prompt="sys",
                text_context="text",
                page_images=[],
                prompt="Extract",
                mode="spatial_helper",
            )

    def test_message_structure_complete(
        self: Self,
        sample_images: list[tuple[int, bytes]],
    ) -> None:
        """Verify the full message structure is OpenAI-compatible."""
        messages = build_vision_messages(
            system_prompt="System prompt",
            text_context="Document text",
            page_images=sample_images,
            prompt="What is the value?",
            mode="spatial_helper",
        )

        assert len(messages) == 2
        assert messages[0] == {
            "role": "system",
            "content": "System prompt",
        }
        assert messages[1]["role"] == "user"
        assert isinstance(messages[1]["content"], list)

        # Every content block must have a "type" key
        for block in messages[1]["content"]:
            assert "type" in block
            assert block["type"] in ("text", "image_url")
