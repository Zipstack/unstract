"""Unit tests for the AWS Bedrock LLM and embedding adapters.

Covers the auth_type selector behaviour added alongside the IAM Role /
Instance Profile mode, plus backwards compatibility for legacy adapter
configurations stored before auth_type existed.

Also covers routing between the two AWS Bedrock endpoints -- the classic
bedrock-runtime Converse/Invoke surface and the OpenAI-compatible
bedrock-mantle endpoint -- and the per-family reasoning shape that goes with
each.
"""

import logging

import pytest

from unstract.sdk1.adapters.base1 import (
    AWSBedrockEmbeddingParameters,
    AWSBedrockLLMParameters,
)

# ── LLM: validate auth_type semantics ────────────────────────────────────────


def test_llm_legacy_no_auth_type_keeps_keys() -> None:
    """Legacy adapters without auth_type must keep working unchanged."""
    out = AWSBedrockLLMParameters.validate(
        {
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "AKIAFAKE",
            "aws_secret_access_key": "secret",
        }
    )
    assert out["aws_access_key_id"] == "AKIAFAKE"
    assert out["aws_secret_access_key"] == "secret"
    assert out["aws_region_name"] == "us-east-1"
    assert "auth_type" not in out


def test_llm_access_keys_mode_keeps_keys_and_strips_auth_type() -> None:
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "access_keys",
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "AKIAFAKE",
            "aws_secret_access_key": "secret",
        }
    )
    assert out["aws_access_key_id"] == "AKIAFAKE"
    assert out["aws_secret_access_key"] == "secret"
    assert "auth_type" not in out


def test_llm_iam_role_mode_drops_keys_even_when_present() -> None:
    """IAM Role mode unconditionally drops access keys.

    A saved adapter switched into IAM mode must not silently leak the
    previously stored long-lived credentials.
    """
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "STALE_KEY",
            "aws_secret_access_key": "STALE_SECRET",
        }
    )
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out
    assert out["aws_region_name"] == "us-east-1"
    assert "auth_type" not in out


def test_llm_iam_role_mode_with_no_keys() -> None:
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "region_name": "us-east-1",
        }
    )
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out


def test_llm_access_keys_mode_blank_keys_raises() -> None:
    """Blank values must surface a clear error.

    Falling through to boto3's default chain would hide the user's
    misconfiguration and authenticate with whatever ambient creds the
    host happens to have.
    """
    with pytest.raises(ValueError, match="aws_access_key_id is required"):
        AWSBedrockLLMParameters.validate(
            {
                "auth_type": "access_keys",
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "region_name": "us-east-1",
                "aws_access_key_id": "",
                "aws_secret_access_key": "",
            }
        )


def test_llm_access_keys_mode_whitespace_keys_raises() -> None:
    with pytest.raises(ValueError, match="aws_secret_access_key is required"):
        AWSBedrockLLMParameters.validate(
            {
                "auth_type": "access_keys",
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "region_name": "us-east-1",
                "aws_access_key_id": "AKIAFAKE",
                "aws_secret_access_key": "   ",
            }
        )


def test_llm_unknown_auth_type_raises() -> None:
    """A typo or non-UI client must not silently fall through."""
    with pytest.raises(ValueError, match="Unknown auth_type"):
        AWSBedrockLLMParameters.validate(
            {
                "auth_type": "access_key",  # typo: missing 's'
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "region_name": "us-east-1",
                "aws_access_key_id": "AKIAFAKE",
                "aws_secret_access_key": "secret",
            }
        )


def test_llm_unknown_bearer_token_typo_raises() -> None:
    with pytest.raises(ValueError, match="Unknown auth_type"):
        AWSBedrockLLMParameters.validate(
            {
                "auth_type": "bearer-token",  # typo: hyphen instead of underscore
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "region_name": "us-east-1",
                "aws_bearer_token": "bedrock-key-abc",
            }
        )


def test_llm_other_params_preserved_through_strip() -> None:
    """Non-credential params survive the auth-type handling.

    model_id, aws_profile_name, region, and thinking config must pass
    through both the strip and the resolver unchanged.
    """
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "anthropic.claude-3-7-sonnet-20250219-v1:0",
            "region_name": "us-east-1",
            "aws_profile_name": "dev-profile",
            "model_id": (
                "arn:aws:bedrock:us-east-1:1234:application-inference-profile/abc"
            ),
            "enable_thinking": True,
            "budget_tokens": 4096,
        }
    )
    assert out["aws_profile_name"] == "dev-profile"
    assert out["aws_region_name"] == "us-east-1"
    assert out["model_id"].endswith("application-inference-profile/abc")
    assert out["thinking"] == {"type": "enabled", "budget_tokens": 4096}


# ── LLM: bearer token (AWS_BEARER_TOKEN_BEDROCK) ─────────────────────────────


def test_llm_bearer_token_mode_translates_to_api_key() -> None:
    """Bearer token is exposed to LiteLLM under its `api_key` kwarg."""
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "bedrock-key-abc",
        }
    )
    assert out["api_key"] == "bedrock-key-abc"
    assert "aws_bearer_token" not in out
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out
    assert "auth_type" not in out


def test_llm_bearer_token_mode_drops_stale_access_keys() -> None:
    """Switching a saved adapter to bearer mode must not leak old access keys."""
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "STALE_KEY",
            "aws_secret_access_key": "STALE_SECRET",
            "aws_bearer_token": "bedrock-key-abc",
        }
    )
    assert out["api_key"] == "bedrock-key-abc"
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out


def test_llm_bearer_token_mode_blank_token_raises() -> None:
    with pytest.raises(ValueError, match="aws_bearer_token is required"):
        AWSBedrockLLMParameters.validate(
            {
                "auth_type": "bearer_token",
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "region_name": "us-east-1",
                "aws_bearer_token": "",
            }
        )


def test_llm_bearer_token_mode_whitespace_token_raises() -> None:
    with pytest.raises(ValueError, match="aws_bearer_token is required"):
        AWSBedrockLLMParameters.validate(
            {
                "auth_type": "bearer_token",
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "region_name": "us-east-1",
                "aws_bearer_token": "   ",
            }
        )


def test_llm_bearer_token_mode_missing_token_raises() -> None:
    """Field absent (not just blank) must surface the same clear error."""
    with pytest.raises(ValueError, match="aws_bearer_token is required"):
        AWSBedrockLLMParameters.validate(
            {
                "auth_type": "bearer_token",
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
                "region_name": "us-east-1",
            }
        )


def test_llm_bearer_token_strips_surrounding_whitespace() -> None:
    """Stray whitespace around a pasted key must not reach the header.

    Storing the unstripped value would produce
    ``Authorization: Bearer  <token> `` which AWS rejects with an opaque 401.
    """
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "  bedrock-key-abc  ",
        }
    )
    assert out["api_key"] == "bedrock-key-abc"


def test_llm_bearer_token_survives_revalidation() -> None:
    """Bearer-mode kwargs must round-trip through a second validate() call.

    ``LLM.complete()`` re-runs ``validate({**self.kwargs, **kwargs})`` on
    every call. The second pass has no ``auth_type`` and no
    ``aws_bearer_token`` (both stripped on the first pass), so the resolver
    can't re-translate. ``api_key`` must survive Pydantic's
    ``model_dump()`` on the round-trip — otherwise LiteLLM falls through
    to SigV4 signing and 401s with "Unable to locate credentials".
    """
    first = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "bedrock-key-abc",
        }
    )
    assert first["api_key"] == "bedrock-key-abc"

    second = AWSBedrockLLMParameters.validate({**first, "max_tokens": 100})
    assert second["api_key"] == "bedrock-key-abc"


def test_llm_iam_role_drops_stale_bearer_token() -> None:
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "STALE_TOKEN",
        }
    )
    assert "aws_bearer_token" not in out
    assert "api_key" not in out


def test_llm_access_keys_drops_stale_bearer_token() -> None:
    out = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "access_keys",
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "AKIAFAKE",
            "aws_secret_access_key": "secret",
            "aws_bearer_token": "STALE_TOKEN",
        }
    )
    assert "aws_bearer_token" not in out
    assert "api_key" not in out
    assert out["aws_access_key_id"] == "AKIAFAKE"


def test_llm_legacy_drops_stray_bearer_token() -> None:
    """Legacy mode (no auth_type) must not stealth-promote a bearer token.

    Auto-translating would silently override env-injected
    ``AWS_BEARER_TOKEN_BEDROCK`` or boto3 default-chain credentials with
    no log line; opting into bearer auth must be explicit.
    """
    out = AWSBedrockLLMParameters.validate(
        {
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "STRAY_TOKEN",
        }
    )
    assert "aws_bearer_token" not in out
    assert "api_key" not in out


# ── LLM: Bedrock Guardrails ──────────────────────────────────────────────────


def _llm_base() -> dict:
    return {
        "auth_type": "access_keys",
        "model": "anthropic.claude-3-haiku-20240307-v1:0",
        "region_name": "us-east-1",
        "aws_access_key_id": "AKIAFAKE",
        "aws_secret_access_key": "secret",
    }


def test_llm_guardrail_packs_into_litellm_kwarg() -> None:
    out = AWSBedrockLLMParameters.validate(
        {
            **_llm_base(),
            "guardrail_identifier": "ff6ujrregl1q",
            "guardrail_version": "DRAFT",
            "guardrail_trace": "enabled",
        }
    )
    assert out["guardrailConfig"] == {
        "guardrailIdentifier": "ff6ujrregl1q",
        "guardrailVersion": "DRAFT",
        "trace": "enabled",
    }
    assert "guardrail_identifier" not in out


def test_llm_guardrail_omitted_drops_key() -> None:
    out = AWSBedrockLLMParameters.validate(_llm_base())
    assert "guardrailConfig" not in out


def test_llm_guardrail_identifier_without_version_raises() -> None:
    """Bedrock rejects identifier without version with an opaque error — fail fast."""
    with pytest.raises(ValueError, match="guardrail_version is required"):
        AWSBedrockLLMParameters.validate(
            {**_llm_base(), "guardrail_identifier": "ff6ujrregl1q"}
        )


def test_llm_guardrail_whitespace_identifier_treated_as_absent() -> None:
    out = AWSBedrockLLMParameters.validate({**_llm_base(), "guardrail_identifier": "   "})
    assert "guardrailConfig" not in out


def test_llm_guardrail_whitespace_version_raises() -> None:
    with pytest.raises(ValueError, match="guardrail_version is required"):
        AWSBedrockLLMParameters.validate(
            {
                **_llm_base(),
                "guardrail_identifier": "ff6ujrregl1q",
                "guardrail_version": "   ",
            }
        )


def test_llm_guardrail_strips_surrounding_whitespace() -> None:
    out = AWSBedrockLLMParameters.validate(
        {
            **_llm_base(),
            "guardrail_identifier": "  ff6ujrregl1q  ",
            "guardrail_version": "  DRAFT  ",
        }
    )
    assert out["guardrailConfig"]["guardrailIdentifier"] == "ff6ujrregl1q"
    assert out["guardrailConfig"]["guardrailVersion"] == "DRAFT"


def test_llm_guardrail_survives_revalidation() -> None:
    """`LLM.complete()` re-validates self.kwargs — guardrailConfig must round-trip."""
    first = AWSBedrockLLMParameters.validate(
        {**_llm_base(), "guardrail_identifier": "g", "guardrail_version": "1"}
    )
    second = AWSBedrockLLMParameters.validate(dict(first))
    assert second["guardrailConfig"] == first["guardrailConfig"]


# ── Embedding: same auth_type matrix ─────────────────────────────────────────


def test_embedding_legacy_no_auth_type_keeps_keys() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "AKIAFAKE",
            "aws_secret_access_key": "secret",
        }
    )
    assert out["aws_access_key_id"] == "AKIAFAKE"
    assert out["aws_secret_access_key"] == "secret"
    assert "auth_type" not in out


def test_embedding_access_keys_mode_keeps_keys() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "access_keys",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "AKIAFAKE",
            "aws_secret_access_key": "secret",
        }
    )
    assert out["aws_access_key_id"] == "AKIAFAKE"
    assert out["aws_secret_access_key"] == "secret"
    assert "auth_type" not in out


def test_embedding_iam_role_mode_drops_stale_keys() -> None:
    """Embedding-side parity with the LLM stale-key fix."""
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "STALE_KEY",
            "aws_secret_access_key": "STALE_SECRET",
        }
    )
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out
    assert out["aws_region_name"] == "us-east-1"


def test_embedding_iam_role_mode_with_no_keys() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
        }
    )
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out


def test_embedding_access_keys_mode_blank_keys_raises() -> None:
    with pytest.raises(ValueError, match="aws_access_key_id is required"):
        AWSBedrockEmbeddingParameters.validate(
            {
                "auth_type": "access_keys",
                "model": "amazon.titan-embed-text-v2:0",
                "region_name": "us-east-1",
                "aws_access_key_id": "",
                "aws_secret_access_key": "",
            }
        )


def test_embedding_unknown_auth_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown auth_type"):
        AWSBedrockEmbeddingParameters.validate(
            {
                "auth_type": "iamrole",  # typo
                "model": "amazon.titan-embed-text-v2:0",
                "region_name": "us-east-1",
            }
        )


def test_embedding_unknown_bearer_token_typo_raises() -> None:
    with pytest.raises(ValueError, match="Unknown auth_type"):
        AWSBedrockEmbeddingParameters.validate(
            {
                "auth_type": "bearer-token",  # typo: hyphen instead of underscore
                "model": "amazon.titan-embed-text-v2:0",
                "region_name": "us-east-1",
                "aws_bearer_token": "bedrock-key-abc",
            }
        )


def test_embedding_region_required_when_absent() -> None:
    """aws_region_name is still mandatory even though credentials are not."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AWSBedrockEmbeddingParameters.validate(
            {
                "auth_type": "iam_role",
                "model": "amazon.titan-embed-text-v2:0",
            }
        )


# ── Embedding: bearer token (AWS_BEARER_TOKEN_BEDROCK) ───────────────────────


def test_embedding_bearer_token_mode_translates_to_api_key() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "bedrock-key-abc",
        }
    )
    assert out["api_key"] == "bedrock-key-abc"
    assert "aws_bearer_token" not in out
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out
    assert "auth_type" not in out


def test_embedding_bearer_token_mode_drops_stale_access_keys() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "STALE_KEY",
            "aws_secret_access_key": "STALE_SECRET",
            "aws_bearer_token": "bedrock-key-abc",
        }
    )
    assert out["api_key"] == "bedrock-key-abc"
    assert "aws_access_key_id" not in out
    assert "aws_secret_access_key" not in out


def test_embedding_bearer_token_mode_blank_token_raises() -> None:
    with pytest.raises(ValueError, match="aws_bearer_token is required"):
        AWSBedrockEmbeddingParameters.validate(
            {
                "auth_type": "bearer_token",
                "model": "amazon.titan-embed-text-v2:0",
                "region_name": "us-east-1",
                "aws_bearer_token": "",
            }
        )


def test_embedding_bearer_token_mode_whitespace_token_raises() -> None:
    with pytest.raises(ValueError, match="aws_bearer_token is required"):
        AWSBedrockEmbeddingParameters.validate(
            {
                "auth_type": "bearer_token",
                "model": "amazon.titan-embed-text-v2:0",
                "region_name": "us-east-1",
                "aws_bearer_token": "   ",
            }
        )


def test_embedding_bearer_token_mode_missing_token_raises() -> None:
    with pytest.raises(ValueError, match="aws_bearer_token is required"):
        AWSBedrockEmbeddingParameters.validate(
            {
                "auth_type": "bearer_token",
                "model": "amazon.titan-embed-text-v2:0",
                "region_name": "us-east-1",
            }
        )


def test_embedding_bearer_token_strips_surrounding_whitespace() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "  bedrock-key-abc  ",
        }
    )
    assert out["api_key"] == "bedrock-key-abc"


def test_embedding_bearer_token_survives_revalidation() -> None:
    """Defensive parity with the LLM round-trip test."""
    first = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "bedrock-key-abc",
        }
    )
    assert first["api_key"] == "bedrock-key-abc"

    second = AWSBedrockEmbeddingParameters.validate({**first})
    assert second["api_key"] == "bedrock-key-abc"


def test_embedding_iam_role_drops_stale_bearer_token() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "STALE_TOKEN",
        }
    )
    assert "aws_bearer_token" not in out
    assert "api_key" not in out


def test_embedding_access_keys_drops_stale_bearer_token() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "auth_type": "access_keys",
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_access_key_id": "AKIAFAKE",
            "aws_secret_access_key": "secret",
            "aws_bearer_token": "STALE_TOKEN",
        }
    )
    assert "aws_bearer_token" not in out
    assert "api_key" not in out
    assert out["aws_access_key_id"] == "AKIAFAKE"


def test_embedding_legacy_drops_stray_bearer_token() -> None:
    out = AWSBedrockEmbeddingParameters.validate(
        {
            "model": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "aws_bearer_token": "STRAY_TOKEN",
        }
    )
    assert "aws_bearer_token" not in out
    assert "api_key" not in out


# ── LLM: Bedrock Mantle routing ──────────────────────────────────────────────
#
# AWS serves two disjoint model-id namespaces behind the Bedrock brand: the
# classic bedrock-runtime Converse/Invoke surface (LiteLLM `bedrock/`) and the
# OpenAI-compatible bedrock-mantle endpoint (LiteLLM `bedrock_mantle/`). The
# ids look confusingly alike -- `openai.gpt-oss-120b-1:0` is Converse while
# `openai.gpt-oss-120b` is Mantle -- so routing is decided by an exact lookup
# in LiteLLM's registry, never a family prefix.

_LLM_BASE: dict[str, str] = {
    "region_name": "us-east-1",
    "aws_access_key_id": "AKIAFAKE",
    "aws_secret_access_key": "secret",
}


def _validate_llm(**overrides: object) -> dict[str, object]:
    return AWSBedrockLLMParameters.validate({**_LLM_BASE, **overrides})


@pytest.mark.parametrize(
    "model",
    [
        "openai.gpt-5.6-terra",
        "openai.gpt-5.6-sol",
        "openai.gpt-5.6-luna",
        "openai.gpt-oss-120b",
        "google.gemma-4-31b",
        "xai.grok-4.3",
    ],
)
def test_llm_mantle_models_route_to_bedrock_mantle(model: str) -> None:
    assert _validate_llm(model=model)["model"] == f"bedrock_mantle/{model}"


@pytest.mark.parametrize(
    "model",
    [
        # Anthropic and Amazon foundation models are Converse-only.
        "anthropic.claude-3-haiku-20240307-v1:0",
        "amazon.titan-text-express-v1",
        # Converse twin of a Mantle model -- the `-1:0` suffix is the whole
        # difference, which is why an exact match matters.
        "openai.gpt-oss-120b-1:0",
        # Cross-Region inference profile ids belong to bedrock-runtime, not
        # Mantle (Mantle is in-Region only).
        "us.openai.gpt-5.6-terra",
        "global.openai.gpt-5.6-terra",
        # Application Inference Profile ARN.
        "arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/abcd",
    ],
)
def test_llm_non_mantle_models_keep_standard_bedrock_route(model: str) -> None:
    assert _validate_llm(model=model)["model"] == f"bedrock/{model}"


def test_llm_unknown_mantle_model_falls_back_to_standard_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Mantle model the loaded registry has not catalogued routes to `bedrock/`.

    This is the failure that bites when AWS ships a Mantle model before LiteLLM
    catalogues it: routing degrades silently to the classic endpoint, where the
    request fails with an opaque AWS error. Pinned here so the fallback is a
    known, documented property rather than an accident of registry contents.
    """
    import litellm

    pruned = {
        k: v
        for k, v in litellm.model_cost.items()
        if k != "bedrock_mantle/openai.gpt-5.6-terra"
    }
    monkeypatch.setattr(litellm, "model_cost", pruned)

    assert (
        _validate_llm(model="openai.gpt-5.6-terra")["model"]
        == "bedrock/openai.gpt-5.6-terra"
    )


@pytest.mark.parametrize(
    "model",
    ["bedrock/openai.gpt-5.6-terra", "bedrock_mantle/anthropic.claude-3-haiku"],
)
def test_llm_explicit_prefix_is_respected(model: str) -> None:
    """An operator-supplied prefix overrides the registry lookup."""
    assert _validate_llm(model=model)["model"] == model


def test_llm_routing_is_idempotent_across_revalidation() -> None:
    """Re-validating an already validated config must be a no-op.

    ``LLM.complete()`` re-validates kwargs on every call, so validate() has to
    be a fixed point -- otherwise the provider prefix would compound.
    """
    first = _validate_llm(model="openai.gpt-5.6-terra")
    second = AWSBedrockLLMParameters.validate(dict(first))
    assert first["model"] == second["model"] == "bedrock_mantle/openai.gpt-5.6-terra"


# ── LLM: params the Mantle endpoint cannot honour ────────────────────────────


def test_llm_mantle_strips_guardrail_and_aip_arn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Guardrails and Application Inference Profiles are Converse-only features.

    LiteLLM drops them silently on the Mantle route, which would leave an
    operator believing a guardrail is enforced when it is not.
    """
    with caplog.at_level(logging.WARNING):
        out = _validate_llm(
            model="openai.gpt-5.6-terra",
            model_id="arn:aws:bedrock:us-east-1:000000000000:application-inference-profile/abcd",
            guardrail_identifier="ff6ujrregl1q",
            guardrail_version="1",
        )
    assert not out.get("guardrailConfig")
    assert not out.get("model_id")
    assert "Bedrock Guardrails" in caplog.text
    assert "Application Inference Profile" in caplog.text


def test_llm_mantle_strip_warns_once_not_per_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`LLM.complete()` re-validates on every call, so the warning must not repeat.

    The first pass removes the keys, so a second validation of the already
    validated payload has nothing left to strip. A reorder that moved the strip
    after the Pydantic dump would emit this warning on every completion.
    """
    with caplog.at_level(logging.WARNING):
        first = _validate_llm(
            model="openai.gpt-5.6-terra",
            guardrail_identifier="ff6ujrregl1q",
            guardrail_version="1",
        )
        warnings_after_first = len(caplog.records)
        AWSBedrockLLMParameters.validate(dict(first))

    assert warnings_after_first == 1
    assert len(caplog.records) == 1


def test_llm_standard_bedrock_keeps_guardrail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        out = _validate_llm(
            model="anthropic.claude-3-haiku-20240307-v1:0",
            guardrail_identifier="ff6ujrregl1q",
            guardrail_version="1",
        )
    assert out["guardrailConfig"] == {
        "guardrailIdentifier": "ff6ujrregl1q",
        "guardrailVersion": "1",
    }
    assert "Mantle" not in caplog.text


def test_llm_mantle_without_guardrail_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        _validate_llm(model="openai.gpt-5.6-terra")
    assert "Mantle" not in caplog.text


def test_llm_mantle_auth_modes_are_unchanged() -> None:
    """Routing must not disturb credential resolution."""
    keys = _validate_llm(model="openai.gpt-5.6-terra", auth_type="access_keys")
    assert keys["aws_access_key_id"] == "AKIAFAKE"
    assert keys["aws_secret_access_key"] == "secret"

    bearer = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "bearer_token",
            "model": "openai.gpt-5.6-terra",
            "region_name": "us-east-1",
            "aws_bearer_token": "BEDROCK_API_KEY",
        }
    )
    assert bearer["api_key"] == "BEDROCK_API_KEY"
    assert "aws_bearer_token" not in bearer

    iam = AWSBedrockLLMParameters.validate(
        {
            "auth_type": "iam_role",
            "model": "openai.gpt-5.6-terra",
            "region_name": "us-east-1",
        }
    )
    assert "aws_access_key_id" not in iam
    assert iam["aws_region_name"] == "us-east-1"


# ── LLM: reasoning shape per model family ────────────────────────────────────
#
# Anthropic models take a `thinking` block; every other reasoning-capable
# family takes `reasoning_effort`, which LiteLLM maps to that family's own wire
# field. Emitting the Anthropic shape for a non-Anthropic model is a silent
# no-op, which is why the switch never did anything outside Claude.


def test_llm_thinking_uses_anthropic_shape_for_claude() -> None:
    out = _validate_llm(
        model="anthropic.claude-3-7-sonnet-20250219-v1:0",
        enable_thinking=True,
        budget_tokens=2048,
    )
    assert out["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert "reasoning_effort" not in out
    assert out["temperature"] == 1


@pytest.mark.parametrize(
    "model",
    [
        "openai.gpt-5.6-terra",  # Mantle -> reasoning.effort
        "openai.gpt-oss-120b-1:0",  # Converse -> additionalModelRequestFields
        "amazon.nova-2-lite-v1:0",  # Converse -> reasoningConfig
    ],
)
def test_llm_thinking_uses_reasoning_effort_for_non_anthropic(model: str) -> None:
    out = _validate_llm(model=model, enable_thinking=True)
    assert out["reasoning_effort"] == "medium"
    assert "thinking" not in out
    assert out["temperature"] == 1


def test_llm_explicit_reasoning_effort_is_preserved() -> None:
    out = _validate_llm(
        model="openai.gpt-5.6-terra", enable_thinking=True, reasoning_effort="high"
    )
    assert out["reasoning_effort"] == "high"


def test_llm_reasoning_disabled_emits_neither_shape() -> None:
    """A declared Pydantic field would otherwise re-emit `reasoning_effort=None`."""
    for model in ("openai.gpt-5.6-terra", "anthropic.claude-3-haiku-20240307-v1:0"):
        out = _validate_llm(model=model)
        assert "reasoning_effort" not in out
        assert "thinking" not in out


def test_llm_reasoning_survives_revalidation() -> None:
    """Reasoning state must round-trip, since kwargs are re-validated per call."""
    first = _validate_llm(model="openai.gpt-5.6-terra", enable_thinking=True)
    second = AWSBedrockLLMParameters.validate(dict(first))
    assert second["reasoning_effort"] == "medium"
    assert second["temperature"] == 1

    claude_first = _validate_llm(
        model="anthropic.claude-3-7-sonnet-20250219-v1:0",
        enable_thinking=True,
        budget_tokens=1024,
    )
    claude_second = AWSBedrockLLMParameters.validate(dict(claude_first))
    assert claude_second["thinking"] == {"type": "enabled", "budget_tokens": 1024}
