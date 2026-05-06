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
