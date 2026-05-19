"""Unit tests for the AWS Bedrock LLM and embedding adapters.

Covers the auth_type selector behaviour added alongside the IAM Role /
Instance Profile mode, plus backwards compatibility for legacy adapter
configurations stored before auth_type existed.
"""

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
