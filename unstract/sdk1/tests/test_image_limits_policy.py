"""Tests for turning resolved image limits into enforceable checks.

The policy layer decides the effective page cap (image count, the
LLMWhisperer ceiling, operator ceilings; the context-token estimate only
warns), the raw-byte budget derived from a wire limit, per-image checks,
and the user-facing messages.
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


def _own_estimate(limits: ImageRequestLimits, per_page: int = 1500) -> ImageRequestLimits:
    """``limits`` with a model-specific tokens-per-page estimate (not the default)."""
    estimate = dataclasses.replace(
        limits.tokens_per_image, value=per_page, from_default=False
    )
    return dataclasses.replace(limits, tokens_per_image=estimate)


@pytest.fixture(autouse=True)
def _no_ambient_image_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rollout and ceiling expectations must not depend on the shell running
    # the tests (``assert 200 == 90`` when VLM_IMAGE_ANSWER_PAGE_CAP is set).
    for name in (
        "VLM_IMAGE_ANSWER_PAGE_CAP",
        "VLM_IMAGE_ANSWER_MAX_TOTAL_MB",
        policy_mod.ENFORCE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


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
        assert policy_mod.ENFORCE_PER_IMAGE_LIMITS is True
        assert policy_mod.ASSUMED_PAGE_BYTES == 250_000


class TestComputePageBudget:
    def test_image_count_binds(self) -> None:
        budget = compute_page_budget(BEDROCK, context_tokens=200_000)
        assert isinstance(budget, PageBudget)
        assert budget.max_pages == 20
        assert budget.binding == "images"

    def test_context_tokens_never_bind_even_with_a_model_estimate(self) -> None:
        # (400k - 4k) / 1500 = 264 pages fit by the estimate; the token term
        # is warn only, so the budget stays at the next real limit.
        budget = compute_page_budget(_own_estimate(OPENAI), context_tokens=400_000)
        assert budget.max_pages == 999
        assert budget.binding == "llmwhisperer"
        assert budget.terms["tokens"] is None
        assert budget.advisory_token_pages == 264

    def test_unknown_context_skips_the_token_term(self) -> None:
        budget = compute_page_budget(OPENAI, context_tokens=None)
        assert budget.binding == "llmwhisperer"
        assert budget.max_pages == 999

    def test_json_max_input_tokens_override_beats_litellm(self) -> None:
        limits = _with(_own_estimate(OPENAI), max_input_tokens=100_000)
        budget = compute_page_budget(limits, context_tokens=1_000_000)
        assert budget.advisory_token_pages == (100_000 - 4_000) // 1500
        assert budget.context_tokens == 100_000

    def test_default_token_estimate_is_advisory(self) -> None:
        # The context-window term is warn-only for every estimate. With the
        # unverified default (1,500 tokens per page) enforcing it would cap
        # 128K-context gpt-4o at 82 pages, below what real pages (~765-1,105
        # tokens) fit; the 82 is reported as an advisory only.
        budget = compute_page_budget(OPENAI, context_tokens=128_000)
        assert budget.binding == "llmwhisperer"
        assert budget.terms["tokens"] is None
        assert budget.advisory_token_pages == 82

    def test_default_token_estimate_is_reported_when_exceeded(self) -> None:
        policy = ImageModePolicy.from_limits([OPENAI], token_budgets=[128_000])
        assert policy.page_budget.max_pages == 999
        lines = policy.advisories(page_count=90)
        assert any("128,000-token context window" in line for line in lines)
        assert not any(
            "context window" in line for line in policy.advisories(page_count=80)
        )

    def test_model_specific_estimate_is_warn_only(self) -> None:
        # User decision (UN-4427 O4): a per-model tokens_per_image is still an
        # estimate, so it warns and never rejects.
        budget = compute_page_budget(_own_estimate(OPENAI), context_tokens=128_000)
        assert budget.binding == "llmwhisperer"
        assert budget.max_pages == 999
        assert budget.advisory_token_pages == 82

    @pytest.mark.parametrize("own_estimate", [False, True])
    def test_document_over_the_estimate_is_accepted_and_warned(
        self, own_estimate: bool
    ) -> None:
        limits = _own_estimate(OPENAI) if own_estimate else OPENAI
        policy = ImageModePolicy.from_limits([limits], token_budgets=[128_000])
        pages = [(n, minimal_png()) for n in range(1, 91)]
        check_page_set(policy, pages, page_store_dir=DIR)  # 90 > 82: no raise
        lines = policy.advisories(page_count=90)
        assert any("may exceed the 128,000-token context window" in ln for ln in lines)
        wording = "for this model" if own_estimate else "unverified default"
        assert any(wording in line for line in lines)

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


class TestPolicyFromLimits:
    def test_single_llm(self) -> None:
        policy = ImageModePolicy.from_limits([BEDROCK], token_budgets=[200_000])
        assert policy.model_aware is True
        assert policy.page_budget.max_pages == 20
        assert policy.max_request_bytes == 20_000_000
        assert policy.max_image_bytes == 3_750_000
        assert policy.max_image_px == 8000

    @pytest.mark.parametrize("order", ["strict_last", "strict_first"])
    def test_min_across_llms_and_records_who_bound(self, order: str) -> None:
        # Both orders, so "last LLM wins" cannot pass for "strictest wins".
        resolved = [OPENAI, BEDROCK] if order == "strict_last" else [BEDROCK, OPENAI]
        policy = ImageModePolicy.from_limits(resolved, token_budgets=[None, None])
        assert policy.page_budget.max_pages == 20
        assert policy.page_budget.limits is BEDROCK
        assert policy.max_request_bytes == 20_000_000
        assert policy.request_bytes_source() is BEDROCK

    @pytest.mark.parametrize("order", ["px_model_first", "px_model_last"])
    def test_per_image_minimum_across_two_llms(self, order: str) -> None:
        # One LLM has the smaller pixel bound, the other the smaller byte
        # bound; each per-image limit is the strictest one and keeps its model.
        small_px = _with(OPENAI, max_image_px=1000, max_image_bytes=50_000_000)
        small_bytes = _with(ANTHROPIC, max_image_px=8000, max_image_bytes=400)
        resolved = (
            [small_px, small_bytes]
            if order == "px_model_first"
            else [small_bytes, small_px]
        )
        policy = ImageModePolicy.from_limits(resolved)
        assert policy.max_image_px == 1000
        assert policy.max_image_px_source is small_px
        assert policy.max_image_bytes == 400 * 3 // 4  # base64-counted
        assert policy.max_image_bytes_source is small_bytes

        with pytest.raises(PageImageTooLargeError) as px_err:
            check_page_set(policy, [(1, _png(1240, 1754))], page_store_dir=DIR)
        assert "`gpt-5.6` on OpenAI" in str(px_err.value)
        with pytest.raises(PageImageTooLargeError) as byte_err:
            check_page_set(policy, [(1, b"x" * 500)], page_store_dir=DIR)
        assert "`claude-sonnet-4-5` on Anthropic" in str(byte_err.value)
        assert "gpt-5.6" not in str(byte_err.value)

    def test_per_image_message_names_the_model_that_set_the_limit(self) -> None:
        # Mistral sets the page budget (8 images); Bedrock's 3.75 MB per-image
        # limit is the stricter one, so the message must name Bedrock.
        mistral = resolve_image_limits("mistral", "mistral/pixtral-large-latest")
        policy = ImageModePolicy.from_limits([mistral, BEDROCK])
        assert policy.page_budget.limits is mistral
        with pytest.raises(PageImageTooLargeError) as excinfo:
            check_page_set(policy, [(1, b"x" * 4_000_000)], page_store_dir=DIR)
        msg = str(excinfo.value)
        assert "Amazon Bedrock" in msg and "pixtral" not in msg
        text = policy.describe()
        assert "per page image for `anthropic.claude-sonnet-4-5-v1:0`" in text

    def test_many_images_rules_stay_paired_per_model(self) -> None:
        # (5 images, 3000 px) and (50 images, 1000 px): minimising each half
        # separately would build (5, 1000), which no model has.
        a = _with(ANTHROPIC, many_images_threshold=5, many_images_max_px=3000)
        b = _with(OPENAI, many_images_threshold=50, many_images_max_px=1000)
        policy = ImageModePolicy.from_limits([a, b])
        page = _png(2000, 2000)
        check_page_set(policy, [(n, page) for n in range(1, 11)], page_store_dir=DIR)
        with pytest.raises(PageImageTooLargeError) as excinfo:
            check_page_set(policy, [(n, page) for n in range(1, 52)], page_store_dir=DIR)
        assert "more than 50 images" in str(excinfo.value)
        assert "OpenAI" in str(excinfo.value)

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
        assert any("20.0 MB" in line for line in policy.advisories(page_count=3))

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
        # The page alone is too large: splitting cannot fix it.
        assert "splitting the document does not help" in str(err)

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
        msg = str(excinfo.value)
        assert "more than 2 images" in msg
        # Splitting IS the fix under the many-images rule.
        assert "at most 2 pages per request" in msg
        assert "files of at most 2 pages" in msg
        assert "does not help" not in msg

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

    def test_token_advisory_explains_the_estimate(self) -> None:
        policy = ImageModePolicy.from_limits(
            [_own_estimate(OPENAI)], token_budgets=[100_000]
        )
        (line,) = (ln for ln in policy.advisories(page_count=200) if "token" in ln)
        assert "tokens per page" in line and "context window" in line
        assert "about 64 pages fit" in line

    def test_token_advisory_covers_every_llm(self) -> None:
        # Bedrock sets the page budget; the 128K OpenAI model is the one whose
        # context the pages may exceed, and the advisory must name it.
        policy = ImageModePolicy.from_limits(
            [BEDROCK, OPENAI], token_budgets=[None, 128_000]
        )
        lines = policy.advisories(page_count=90)
        assert any("gpt-5.6" in ln and "128,000-token" in ln for ln in lines)

    def test_describe_summarises_the_policy(self) -> None:
        text = ImageModePolicy.from_limits([BEDROCK], token_budgets=[200_000]).describe()
        assert "Amazon Bedrock" in text and "20" in text and "20.0 MB" in text


class TestRolloutBounds:
    """Extraction stays within the plugin's fixed limits during rollout.

    Until the cloud plugin answers with model-aware limits, extraction is
    bounded by its fixed 90 pages / 14 MiB, so it can only get stricter,
    never looser, than answer time.
    """

    def test_legacy_clamp_follows_the_operator_env_overrides(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # While LEGACY is on the env vars REPLACE 90 / 14 MiB; extraction
        # must use them, or it accepts documents the plugin then rejects.
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "40")
        monkeypatch.setenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", "6")
        assert policy_mod.LEGACY_ANSWER_BOUNDS_ACTIVE is True
        kwargs = policy_mod.extraction_bound_kwargs()
        assert kwargs == {
            "page_ceiling": None,
            "bytes_ceiling": 6 * 1024 * 1024,
            "legacy_cap": 40,
        }
        policy = ImageModePolicy.from_limits([OPENAI], **kwargs)
        assert policy.page_budget.max_pages == 40
        assert policy.raw_byte_budget(page_count=10) == 6 * 1024 * 1024
        with pytest.raises(PageCapExceededError):
            check_page_set(
                policy, [(n, minimal_png()) for n in range(1, 61)], page_store_dir=DIR
            )

    def test_legacy_bounds_are_active_and_read_the_legacy_accessors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("VLM_IMAGE_ANSWER_PAGE_CAP", raising=False)
        monkeypatch.delenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", raising=False)
        assert policy_mod.LEGACY_ANSWER_BOUNDS_ACTIVE is True
        kwargs = policy_mod.extraction_bound_kwargs()
        assert kwargs == {
            "page_ceiling": None,
            "bytes_ceiling": 14 * 1024 * 1024,
            "legacy_cap": 90,
        }

    def test_switch_off_leaves_only_operator_ceilings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(policy_mod, "LEGACY_ANSWER_BOUNDS_ACTIVE", False)
        monkeypatch.setenv("VLM_IMAGE_ANSWER_PAGE_CAP", "40")
        monkeypatch.delenv("VLM_IMAGE_ANSWER_MAX_TOTAL_MB", raising=False)
        assert policy_mod.extraction_bound_kwargs() == {
            "page_ceiling": 40,
            "bytes_ceiling": None,
            "legacy_cap": None,
        }

    def test_generous_model_is_held_at_the_legacy_cap(self) -> None:
        policy = ImageModePolicy.from_limits(
            [OPENAI], **policy_mod.extraction_bound_kwargs()
        )
        assert policy.page_budget.max_pages == 90
        assert policy.page_budget.binding == "legacy"

    def test_strict_model_still_binds_below_the_legacy_cap(self) -> None:
        policy = ImageModePolicy.from_limits(
            [BEDROCK], **policy_mod.extraction_bound_kwargs()
        )
        assert policy.page_budget.max_pages == 20
        assert policy.page_budget.binding == "images"

    def test_legacy_page_message_does_not_blame_an_administrator(self) -> None:
        budget = compute_page_budget(OPENAI, context_tokens=None, legacy_cap=90)
        msg = policy_mod.page_cap_message(120, budget, charged=False)
        assert "administrator" not in msg
        assert "90" in msg

    def test_ceiling_bound_bytes_message_names_the_ceiling_not_the_model(self) -> None:
        # Bedrock allows 20 MB on the wire (~15 MB raw); a 1 MiB ceiling binds.
        policy = ImageModePolicy.from_limits([BEDROCK], bytes_ceiling=1024 * 1024)
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            check_page_set(
                policy, [(1, b"x" * 600_000), (2, b"x" * 600_000)], page_store_dir=DIR
            )
        msg = str(excinfo.value)
        assert "20.0 MB request limit" not in msg
        assert "over the 1.0 MiB limit" in msg


class TestByteUnitsInMessages:
    """A message prints its limit and its total in one unit, to 0.1.

    Provider limits are documented in decimal MB; the operator and legacy
    ceilings are MiB (``VLM_IMAGE_ANSWER_MAX_TOTAL_MB`` has always been
    MiB). Rounding to whole units used to print Gemma 4's 3.5 MB as "4 MB"
    and a 14.7 MiB total as "over the 15 MB limit".
    """

    def test_gemma_request_limit_keeps_its_decimal(self) -> None:
        policy = ImageModePolicy.from_limits([GEMMA])
        page = b"x" * 1_400_000
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            check_page_set(policy, [(1, page), (2, page)], page_store_dir=DIR)
        msg = str(excinfo.value)
        assert "total 2.8 MB (3.8 MB once encoded)" in msg
        assert "over the 3.5 MB request limit" in msg
        assert "3.5 MB per request" in policy.describe()

    def test_legacy_ceiling_message_is_in_mib(self) -> None:
        # The 14 MiB legacy ceiling binds under OpenAI's 512 MB limit.
        policy = ImageModePolicy.from_limits(
            [OPENAI], **policy_mod.extraction_bound_kwargs()
        )
        page = b"x" * 7_700_000
        with pytest.raises(PageImageSetTooLargeError) as excinfo:
            check_page_set(policy, [(1, page), (2, page)], page_store_dir=DIR)
        msg = str(excinfo.value)
        assert "total 14.7 MiB" in msg
        assert "over the 14.0 MiB limit" in msg
        assert "15 MB" not in msg and "512" not in msg

    def test_describe_reports_a_binding_ceiling(self) -> None:
        policy = ImageModePolicy.from_limits(
            [OPENAI], **policy_mod.extraction_bound_kwargs()
        )
        text = policy.describe()
        assert "14.0 MiB of page images per request" in text
        assert "512" not in text

    def test_describe_reports_the_model_limit_when_it_is_smaller(self) -> None:
        # Bedrock's 20 MB wire limit (~15 MB raw) is under a 100 MiB ceiling.
        policy = ImageModePolicy.from_limits([BEDROCK], bytes_ceiling=100 * 1024 * 1024)
        text = policy.describe()
        assert "20.0 MB per request" in text
        assert "MiB" not in text

    def test_ceiling_only_policy_reports_the_ceiling(self) -> None:
        policy = ImageModePolicy.ceiling_only(bytes_ceiling=14 * 1024 * 1024)
        assert "14.0 MiB of page images per request" in policy.describe()


class TestAdvisorySink:
    """Advisories reach the user's run log, not only the worker log (O12)."""

    def test_check_page_set_streams_advisories(self) -> None:
        streamed: list[str] = []
        policy = ImageModePolicy.from_limits([OLLAMA]).with_advisory_sink(streamed.append)
        check_page_set(
            policy, [(n, minimal_png()) for n in range(1, 30)], page_store_dir=DIR
        )
        assert streamed and "Ollama" in " ".join(streamed)

    def test_size_advisory_is_streamed(self) -> None:
        streamed: list[str] = []
        policy = ImageModePolicy.from_limits([GEMMA]).with_advisory_sink(streamed.append)
        policy.emit_advisories(page_count=30, include_size=True)
        assert any("request-size limit" in line for line in streamed)

    def test_advisories_can_be_skipped(self) -> None:
        streamed: list[str] = []
        policy = ImageModePolicy.from_limits([OLLAMA]).with_advisory_sink(streamed.append)
        check_page_set(
            policy,
            [(n, minimal_png()) for n in range(1, 30)],
            page_store_dir=DIR,
            emit_advisories=False,
        )
        assert streamed == []

    def test_a_failing_sink_never_breaks_the_check(self) -> None:
        def boom(line: str) -> None:
            raise RuntimeError("log stream down")

        policy = ImageModePolicy.from_limits([OLLAMA]).with_advisory_sink(boom)
        check_page_set(
            policy, [(n, minimal_png()) for n in range(1, 30)], page_store_dir=DIR
        )


class TestEnforceSwitch:
    """``VLM_IMAGE_LIMITS_ENFORCE=false`` falls back to the fixed cap (O13)."""

    def test_enabled_by_default(self) -> None:
        assert policy_mod.model_aware_limits_enabled() is True

    @pytest.mark.parametrize("raw", ["false", "FALSE", "0", "no", "off"])
    def test_false_turns_model_aware_limits_off(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv(policy_mod.ENFORCE_ENV, raw)
        assert policy_mod.model_aware_limits_enabled() is False

    def test_invalid_value_keeps_them_on_and_logs(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(policy_mod.ENFORCE_ENV, "maybe")
        assert policy_mod.model_aware_limits_enabled() is True
        assert any(r.levelname == "ERROR" for r in caplog.records)

    def test_fixed_cap_is_90_pages_and_14_mib(self) -> None:
        policy = ImageModePolicy.ceiling_only(**policy_mod.fixed_cap_bound_kwargs())
        assert policy.page_budget.max_pages == 90
        assert policy.raw_byte_budget(page_count=10) == 14 * 1024 * 1024


class TestEnforceSwitchInsideTheBuilders:
    """The shared builders honour ``VLM_IMAGE_LIMITS_ENFORCE=false`` (O13).

    Consumers (the cloud answer plugin, its backend hooks, the OSS upload
    check) build their policy with these; none of them should have to
    remember to check the switch.
    """

    @pytest.fixture(autouse=True)
    def _switched_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(policy_mod.ENFORCE_ENV, "false")

    @pytest.mark.parametrize("legacy_active", [True, False])
    def test_from_limits_yields_the_fixed_cap(
        self, monkeypatch: pytest.MonkeyPatch, legacy_active: bool
    ) -> None:
        monkeypatch.setattr(policy_mod, "LEGACY_ANSWER_BOUNDS_ACTIVE", legacy_active)
        policy = ImageModePolicy.from_limits(
            [BEDROCK], token_budgets=[200_000], **policy_mod.extraction_bound_kwargs()
        )
        assert policy.model_aware is False
        assert policy.switched_off is True
        assert policy.page_budget.max_pages == 90  # not Bedrock's 20
        assert policy.max_request_bytes is None
        assert policy.max_image_bytes is None
        assert policy.raw_byte_budget(page_count=10) == 14 * 1024 * 1024
        # 30 pages: over Bedrock's 20 images, inside the fixed cap.
        check_page_set(
            policy, [(n, minimal_png()) for n in range(1, 31)], page_store_dir=DIR
        )

    def test_from_limits_without_bounds_is_still_the_fixed_cap(self) -> None:
        policy = ImageModePolicy.from_limits([OPENAI])
        assert policy.page_budget.max_pages == 90
        assert policy.bytes_ceiling == 14 * 1024 * 1024

    def test_a_stricter_bound_still_applies(self) -> None:
        policy = ImageModePolicy.from_limits([OPENAI], legacy_cap=10, bytes_ceiling=1000)
        assert policy.page_budget.max_pages == 10
        assert policy.bytes_ceiling == 1000

    def test_extraction_bounds_are_the_fixed_cap_after_rollout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(policy_mod, "LEGACY_ANSWER_BOUNDS_ACTIVE", False)
        assert policy_mod.extraction_bound_kwargs() == (
            policy_mod.fixed_cap_bound_kwargs()
        )

    def test_compute_page_budget_yields_the_fixed_cap(self) -> None:
        budget = compute_page_budget(BEDROCK, context_tokens=200_000)
        assert budget.max_pages == 90
        assert budget.limits is None

    def test_describe_says_the_switch_is_off(self) -> None:
        text = ImageModePolicy.from_limits([BEDROCK]).describe()
        assert "VLM_IMAGE_LIMITS_ENFORCE=false" in text
        assert "LLM not known" not in text

    def test_switched_off_warning_is_logged_once_per_process(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(policy_mod, "_switched_off_logged", False)
        for _ in range(3):  # e.g. three profile renders
            ImageModePolicy.from_limits([BEDROCK])
        lines = [
            r
            for r in caplog.records
            if r.levelname == "WARNING" and policy_mod.ENFORCE_ENV in r.getMessage()
        ]
        assert len(lines) == 1

    def test_invalid_switch_value_is_logged_once_per_process(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(policy_mod, "_invalid_switch_logged", set())
        monkeypatch.setenv(policy_mod.ENFORCE_ENV, "maybe")
        for _ in range(3):  # read per lookup
            assert policy_mod.model_aware_limits_enabled() is True
        lines = [
            r
            for r in caplog.records
            if r.levelname == "ERROR" and policy_mod.ENFORCE_ENV in r.getMessage()
        ]
        assert len(lines) == 1

    def test_switch_on_keeps_model_aware_limits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(policy_mod.ENFORCE_ENV, "true")
        policy = ImageModePolicy.from_limits([BEDROCK])
        assert policy.model_aware is True
        assert policy.page_budget.max_pages == 20


class TestAdvisoriesCoverEveryLlm:
    """Pass-through advisories are not dropped when another LLM binds (N4)."""

    def test_image_count_advisory_names_the_pass_through_llm(self) -> None:
        # Bedrock (20, enforced) sets the page budget; the Ollama model's
        # advisory default must still be reported.
        policy = ImageModePolicy.from_limits([BEDROCK, OLLAMA])
        assert policy.page_budget.limits.provider_key == "bedrock"
        lines = policy.advisories(page_count=25)
        assert any("llava" in ln and "publishes no image limit" in ln for ln in lines)

    def test_request_size_advisory_for_each_pass_through_llm(self) -> None:
        other = dataclasses.replace(OLLAMA, model="bakllava")
        policy = ImageModePolicy.from_limits([OLLAMA, other])
        lines = [
            ln
            for ln in policy.advisories(page_count=3)
            if "publishes no request-size limit" in ln
        ]
        assert any("`llava`" in ln for ln in lines)
        assert any("`bakllava`" in ln for ln in lines)


class TestFixedCapMessage:
    """One wording for the fixed cap, shared by every site that enforces it."""

    def test_states_the_count_the_cap_and_the_fix(self) -> None:
        msg = policy_mod.fixed_cap_message(
            91, 90, charged=False, pages_to_extract_note=True
        )
        assert msg.startswith("This document has too many pages for image output mode.")
        assert "It has 91 pages, and the limit is 90" in msg
        assert "or use a text output mode instead." in msg
        assert "No pages were converted or charged." in msg
        assert msg.endswith("does not apply in image output mode.)")

    def test_callers_choose_the_text_mode_advice(self) -> None:
        msg = policy_mod.fixed_cap_message(
            6, 5, switch_to="switch this profile to a text output mode"
        )
        assert msg.endswith("or switch this profile to a text output mode.")
        assert "charged" not in msg and "Pages to extract" not in msg
