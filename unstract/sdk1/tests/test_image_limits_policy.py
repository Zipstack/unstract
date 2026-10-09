"""Tests for turning resolved image limits into enforceable checks.

The policy layer decides the effective page cap (image count, context
tokens, the LLMWhisperer ceiling, operator ceilings), the raw-byte budget
derived from a wire limit, per-image checks, and the user-facing messages.
"""

import dataclasses
import struct
import zlib

import pytest
from unstract.sdk1.adapters.x2text.constants import ImageOutputConstants
from unstract.sdk1.adapters.x2text.page_image_loader import (
    PageCapExceededError,
    PageImageSetTooLargeError,
    PageImageTooLargeError,
)
from unstract.sdk1.utils.image_limits import (
    ImageModePolicy,
    ImageRequestLimits,
    PageBudget,
    check_page_set,
    compute_page_budget,
    estimate_wire_bytes,
    png_dimensions,
    resolve_image_limits,
)
from unstract.sdk1.utils.image_limits import policy as policy_mod

from tests.llmw_image_fixtures import minimal_png

DIR = "/data/extract/doc/pages"


def _png(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    return signature + chunk + b"\x00" * 16


def _with(limits: ImageRequestLimits, **values: int | None) -> ImageRequestLimits:
    """Copy ``limits`` with the given field values replaced."""
    changes = {}
    for name, value in values.items():
        changes[name] = dataclasses.replace(getattr(limits, name), value=value)
    return dataclasses.replace(limits, **changes)


BEDROCK = resolve_image_limits("bedrock", "bedrock/anthropic.claude-sonnet-4-5-v1:0")
OPENAI = resolve_image_limits("openai", "openai/gpt-5.6")
ANTHROPIC = resolve_image_limits("anthropic", "anthropic/claude-sonnet-4-5")
GEMMA = resolve_image_limits("bedrock", "bedrock_mantle/google.gemma-4-31b")
OLLAMA = resolve_image_limits("ollama", "ollama_chat/llava")


class TestConstants:
    def test_llmwhisperer_ceiling_is_a_shared_constant(self) -> None:
        assert ImageOutputConstants.LLMWHISPERER_MAX_PAGES == 999

    def test_tunables_are_module_constants(self) -> None:
        assert policy_mod.PROMPT_TOKENS_RESERVE == 4_000
        assert policy_mod.ENFORCE_CONTEXT_TOKEN_TERM is True
        assert policy_mod.ENFORCE_PER_IMAGE_LIMITS is True
        assert policy_mod.ASSUMED_PAGE_BYTES == 250_000


class TestComputePageBudget:
    def test_image_count_binds(self) -> None:
        budget = compute_page_budget(BEDROCK, context_tokens=200_000)
        assert isinstance(budget, PageBudget)
        assert budget.max_pages == 20
        assert budget.binding == "images"

    def test_context_tokens_bind_on_generous_providers(self) -> None:
        # 1500 images allowed, but (400k - 4k) / 1500 = 264 pages fit.
        budget = compute_page_budget(OPENAI, context_tokens=400_000)
        assert budget.max_pages == 264
        assert budget.binding == "tokens"

    def test_unknown_context_skips_the_token_term(self) -> None:
        budget = compute_page_budget(OPENAI, context_tokens=None)
        assert budget.binding == "llmwhisperer"
        assert budget.max_pages == 999

    def test_json_max_input_tokens_override_beats_litellm(self) -> None:
        limits = _with(OPENAI, max_input_tokens=100_000)
        budget = compute_page_budget(limits, context_tokens=1_000_000)
        assert budget.max_pages == (100_000 - 4_000) // 1500

    def test_token_term_can_be_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(policy_mod, "ENFORCE_CONTEXT_TOKEN_TERM", False)
        budget = compute_page_budget(OPENAI, context_tokens=10_000)
        assert budget.binding == "llmwhisperer"

    def test_operator_ceiling_binds(self) -> None:
        budget = compute_page_budget(OPENAI, context_tokens=None, page_ceiling=50)
        assert budget.max_pages == 50
        assert budget.binding == "ceiling"

    def test_legacy_cap_binds_during_rollout(self) -> None:
        budget = compute_page_budget(OPENAI, context_tokens=None, legacy_cap=90)
        assert budget.max_pages == 90
        assert budget.binding == "legacy"

    def test_ceiling_never_raises_a_model_limit(self) -> None:
        budget = compute_page_budget(BEDROCK, context_tokens=None, page_ceiling=300)
        assert budget.max_pages == 20

    def test_advisory_default_is_not_enforced_but_recorded(self) -> None:
        budget = compute_page_budget(OLLAMA, context_tokens=None)
        assert budget.max_pages == 999
        assert budget.binding == "llmwhisperer"
        assert budget.advisory_max_images == 20

    def test_describe_names_the_binding_term(self) -> None:
        text = compute_page_budget(BEDROCK, context_tokens=None).describe()
        assert "20" in text and "Amazon Bedrock" in text
        tokens = compute_page_budget(OPENAI, context_tokens=400_000).describe()
        assert "context window" in tokens


class TestPolicyFromLimits:
    def test_single_llm(self) -> None:
        policy = ImageModePolicy.from_limits([BEDROCK], token_budgets=[200_000])
        assert policy.model_aware is True
        assert policy.page_budget.max_pages == 20
        assert policy.max_request_bytes == 20_000_000
        assert policy.max_image_bytes == 3_750_000
        assert policy.max_image_px == 8000

    def test_min_across_llms_and_records_who_bound(self) -> None:
        policy = ImageModePolicy.from_limits(
            [OPENAI, BEDROCK], token_budgets=[None, None]
        )
        assert policy.page_budget.max_pages == 20
        assert policy.page_budget.limits is BEDROCK
        assert policy.max_request_bytes == 20_000_000

    def test_ceiling_only_is_not_model_aware(self) -> None:
        policy = ImageModePolicy.ceiling_only(
            page_ceiling=120, bytes_ceiling=14 * 1024 * 1024
        )
        assert policy.model_aware is False
        assert policy.page_budget.max_pages == 120
        assert policy.raw_byte_budget(page_count=10) == 14 * 1024 * 1024
        assert policy.max_image_bytes is None

    def test_ceiling_only_without_ceilings_caps_at_llmwhisperer(self) -> None:
        policy = ImageModePolicy.ceiling_only()
        assert policy.page_budget.max_pages == 999
        assert policy.raw_byte_budget(page_count=10) is None


class TestByteBudgets:
    def test_estimate_wire_bytes_adds_base64_and_text(self) -> None:
        wire = estimate_wire_bytes(3_000_000, page_count=10, prompt_text_bytes=1_000)
        assert wire == 4_000_000 + 1_000 + 10 * policy_mod.PAGE_LABEL_OVERHEAD_BYTES

    def test_raw_byte_budget_from_a_base64_counted_limit(self) -> None:
        policy = ImageModePolicy.from_limits([BEDROCK])
        budget = policy.raw_byte_budget(page_count=10, prompt_text_bytes=1_000)
        text = 1_000 + 10 * policy_mod.PAGE_LABEL_OVERHEAD_BYTES
        assert budget == (20_000_000 - text) * 3 // 4

    def test_unknown_prompt_uses_the_text_reserve(self) -> None:
        policy = ImageModePolicy.from_limits([BEDROCK])
        budget = policy.raw_byte_budget(page_count=10)
        text = policy_mod.TEXT_RESERVE_BYTES + 10 * policy_mod.PAGE_LABEL_OVERHEAD_BYTES
        assert budget == (20_000_000 - text) * 3 // 4

    def test_raw_counted_limit_is_used_as_is(self) -> None:
        limits = dataclasses.replace(
            BEDROCK,
            max_request_bytes=dataclasses.replace(
                BEDROCK.max_request_bytes, value=1_000_000, base64_counted=False
            ),
        )
        policy = ImageModePolicy.from_limits([limits])
        assert policy.raw_byte_budget(page_count=3) == 1_000_000

    def test_operator_bytes_ceiling_tightens(self) -> None:
        policy = ImageModePolicy.from_limits([BEDROCK], bytes_ceiling=1_000)
        assert policy.raw_byte_budget(page_count=3) == 1_000

    def test_advisory_request_bytes_are_not_enforced(self) -> None:
        policy = ImageModePolicy.from_limits([OLLAMA])
        assert policy.raw_byte_budget(page_count=3) is None
        assert any(
            "20 MB" in line or "20,000,000" in line
            for line in policy.advisories(page_count=3)
        )

    def test_gemma_tiny_request_limit_binds(self) -> None:
        policy = ImageModePolicy.from_limits([GEMMA])
        assert policy.raw_byte_budget(page_count=5) < 3_500_000


class TestPngDimensions:
    def test_reads_ihdr(self) -> None:
        assert png_dimensions(_png(1240, 1754)) == (1240, 1754)

    def test_minimal_fixture(self) -> None:
        assert png_dimensions(minimal_png()) == (1, 1)

    def test_truncated_or_foreign_bytes_are_none(self) -> None:
        assert png_dimensions(b"\x89PNG\r\n\x1a\n\x00\x00") is None
        assert png_dimensions(b"not a png at all, honestly") is None
        assert png_dimensions(b"") is None


class TestCheckPageSet:
    def test_within_limits_passes(self) -> None:
        policy = ImageModePolicy.from_limits([BEDROCK])
        check_page_set(
            policy, [(1, minimal_png()), (2, minimal_png())], page_store_dir=DIR
        )

    def test_page_count_over_budget(self) -> None:
        policy = ImageModePolicy.from_limits([BEDROCK])
        pages = [(n, minimal_png()) for n in range(1, 22)]
        with pytest.raises(PageCapExceededError) as excinfo:
            check_page_set(policy, pages, page_store_dir=DIR, charged=True)
        err = excinfo.value
        assert err.page_count == 21 and err.page_cap == 20
        msg = str(err)
        assert "This document has 21 pages" in msg
        assert "Amazon Bedrock" in msg and "20 page images" in msg
        assert "documented" in msg
        assert "already" in msg

    def test_total_bytes_over_budget(self) -> None:
        limits = _with(BEDROCK, max_request_bytes=1_000_000)
        policy = ImageModePolicy.from_limits([limits])
        pages = [(1, b"x" * 500_000), (2, b"x" * 500_000)]
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            check_page_set(policy, pages, page_store_dir=DIR, charged=True)
        msg = str(excinfo.value)
        assert "1.0 MB" in msg and "once encoded" in msg
        assert "Amazon Bedrock" in msg
        assert "already been charged" in msg

    def test_single_page_over_per_image_bytes(self) -> None:
        limits = _with(BEDROCK, max_image_bytes=100)
        policy = ImageModePolicy.from_limits([limits])
        with pytest.raises(PageImageTooLargeError) as excinfo:
            check_page_set(policy, [(1, b"x" * 200)], page_store_dir=DIR)
        err = excinfo.value
        assert err.page_number == 1 and err.limit_kind == "bytes"
        assert "Page 1" in str(err) and "per-image" in str(err)

    def test_single_page_over_pixel_limit(self) -> None:
        limits = _with(BEDROCK, max_image_px=1000)
        policy = ImageModePolicy.from_limits([limits])
        with pytest.raises(PageImageTooLargeError) as excinfo:
            check_page_set(policy, [(1, _png(1240, 1754))], page_store_dir=DIR)
        assert excinfo.value.limit_kind == "pixels"
        assert "1240×1754" in str(excinfo.value)

    def test_many_images_pixel_rule_applies_above_threshold(self) -> None:
        limits = _with(ANTHROPIC, many_images_threshold=2, many_images_max_px=1500)
        policy = ImageModePolicy.from_limits([limits])
        page = _png(1240, 1754)
        check_page_set(policy, [(1, page), (2, page)], page_store_dir=DIR)
        with pytest.raises(PageImageTooLargeError) as excinfo:
            check_page_set(policy, [(1, page), (2, page), (3, page)], page_store_dir=DIR)
        assert "more than 2 images" in str(excinfo.value)

    def test_per_image_checks_can_be_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(policy_mod, "ENFORCE_PER_IMAGE_LIMITS", False)
        limits = _with(BEDROCK, max_image_bytes=100)
        policy = ImageModePolicy.from_limits([limits])
        check_page_set(policy, [(1, b"x" * 200)], page_store_dir=DIR)

    def test_unparseable_png_skips_pixel_check(self) -> None:
        limits = _with(BEDROCK, max_image_px=1)
        policy = ImageModePolicy.from_limits([limits])
        check_page_set(policy, [(1, b"not png")], page_store_dir=DIR)

    def test_pass_through_defaults_warn_instead_of_rejecting(self) -> None:
        policy = ImageModePolicy.from_limits([OLLAMA])
        pages = [(n, minimal_png()) for n in range(1, 30)]
        check_page_set(policy, pages, page_store_dir=DIR)
        lines = policy.advisories(page_count=29)
        assert lines and "Ollama" in " ".join(lines)
        assert any("20" in line for line in lines)


class TestMessages:
    def test_unverified_source_is_called_out(self) -> None:
        azure = resolve_image_limits("azure", "azure/my-dep")
        budget = compute_page_budget(azure, context_tokens=None)
        msg = policy_mod.page_cap_message(60, budget, charged=False)
        assert "Azure OpenAI" in msg
        assert "not confirmed" in msg
        assert "No pages were converted or charged" in msg

    def test_default_on_a_hosted_provider_is_called_out(self) -> None:
        # Grok on Mantle has no documented count: the default applies and is
        # enforced (hosted provider), so the message must say it is a default.
        limits = resolve_image_limits("bedrock", "bedrock_mantle/xai.grok-4.6")
        budget = compute_page_budget(limits, context_tokens=None)
        msg = policy_mod.page_cap_message(60, budget, charged=None)
        assert budget.binding == "images"
        assert "no published limit" in msg
        assert "conservative" in msg
        assert "charged" not in msg

    def test_unknown_provider_is_advisory_only(self) -> None:
        limits = resolve_image_limits("not-a-provider", "x/y")
        policy = ImageModePolicy.from_limits([limits])
        assert policy.page_budget.binding == "llmwhisperer"
        assert any(
            "conservative default" in line for line in policy.advisories(page_count=60)
        )

    def test_token_bound_message_explains_the_estimate(self) -> None:
        budget = compute_page_budget(OPENAI, context_tokens=100_000)
        msg = policy_mod.page_cap_message(200, budget, charged=False)
        assert "tokens per page" in msg and "context window" in msg

    def test_describe_summarises_the_policy(self) -> None:
        text = ImageModePolicy.from_limits([BEDROCK], token_budgets=[200_000]).describe()
        assert "Amazon Bedrock" in text and "20" in text and "20 MB" in text
