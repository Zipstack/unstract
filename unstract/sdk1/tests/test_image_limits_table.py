"""Tests for the bundled vision image-limits table and its loader.

The table is the data the model-aware image-mode checks run on, so these
tests pin its contract: it loads strictly, every provider adapter is
covered, provenance resolves, and an operator override file replaces
entries per provider without a release.
"""

import json
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters as llm_adapters
from unstract.sdk1.utils import image_limits
from unstract.sdk1.utils.image_limits import (
    LIMITS_OVERRIDE_FILE_ENV,
    LimitsSchemaError,
    LimitsTable,
    get_limits_table,
    load_limits_table,
    resolve_image_limits,
)

BUNDLED = Path(image_limits.__file__).parent / "limits.json"
LIMIT_FIELDS = (
    "max_images_per_request",
    "max_request_bytes",
    "max_image_bytes",
    "max_image_px",
    "many_images_threshold",
    "many_images_max_px",
    "max_image_patches",
    "tokens_per_image",
    "max_input_tokens",
)


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    image_limits.clear_limits_cache()
    yield
    image_limits.clear_limits_cache()


def _minimal_table(**providers: dict) -> dict:
    return {
        "_meta": {"schema_version": 1},
        "sources": {"POLICY": {"url": "(policy)", "verified_on": "2026-10-09"}},
        "default": {
            "max_images_per_request": {
                "value": 20,
                "confidence": "unverified",
                "source": "POLICY",
            },
            "max_request_bytes": {
                "value": 20_000_000,
                "confidence": "unverified",
                "source": "POLICY",
                "base64_counted": True,
            },
            "tokens_per_image": {
                "value": 1500,
                "confidence": "unverified",
                "source": "POLICY",
            },
        },
        "providers": providers,
    }


def _provider(**fields: dict) -> dict:
    entry = {"adapter": "x", "display_name": "X", "kind": "hosted", "defaults": {}}
    entry.update(fields)
    return entry


class TestBundledTable:
    def test_loads_strictly_with_schema_version_one(self) -> None:
        table = load_limits_table(BUNDLED)
        assert isinstance(table, LimitsTable)
        assert table.schema_version == 1
        assert table.layer == "shipped"

    def test_every_llm_adapter_provider_has_an_entry(self) -> None:
        table = load_limits_table(BUNDLED)
        for adapter in llm_adapters.values():
            provider = adapter[Common.MODULE].get_provider()
            assert provider in table.providers, provider
        # The Mantle route is keyed separately from the Bedrock adapter.
        assert "bedrock_mantle" in table.providers

    def test_every_provider_declares_adapter_kind_and_label(self) -> None:
        table = load_limits_table(BUNDLED)
        for key, entry in table.providers.items():
            assert entry.adapter, key
            assert entry.kind in {"hosted", "pass_through"}, key
            assert entry.display_name, key

    def test_every_source_reference_resolves(self) -> None:
        table = load_limits_table(BUNDLED)
        for entry in table.providers.values():
            for field in entry.defaults.values():
                for key in field.sources:
                    assert key in table.sources
            for override in entry.overrides:
                for field in override.fields.values():
                    for key in field.sources:
                        assert key in table.sources

    def test_every_inherit_target_exists(self) -> None:
        table = load_limits_table(BUNDLED)
        for entry in table.providers.values():
            for override in entry.overrides:
                if override.inherit:
                    assert override.inherit in table.providers

    def test_default_provides_count_bytes_and_tokens(self) -> None:
        table = load_limits_table(BUNDLED)
        assert table.default["max_images_per_request"].value == 20
        assert table.default["max_request_bytes"].value == 20_000_000
        assert table.default["tokens_per_image"].value == 1500

    def test_key_corrections_from_verification_are_present(self) -> None:
        table = load_limits_table(BUNDLED)
        gemini = table.providers["gemini"].defaults["max_request_bytes"]
        assert gemini.value == 100_000_000  # not the stale 20 MB
        mantle = table.providers["bedrock_mantle"]
        claude = [o for o in mantle.overrides if "claude" in o.pattern][0]
        assert claude.fields["max_request_bytes"].confidence == "unverified"


class TestSchemaValidation:
    def _load(self, tmp_path: Path, data: dict) -> LimitsTable:
        path = tmp_path / "limits.json"
        path.write_text(json.dumps(data))
        return load_limits_table(path)

    def test_unknown_top_level_key_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table()
        data["providerz"] = {}
        with pytest.raises(LimitsSchemaError, match="providerz"):
            self._load(tmp_path, data)

    def test_unknown_limit_field_in_override_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table(
            p=_provider(
                model_overrides=[
                    {
                        "pattern": "x",
                        "max_imagez": {
                            "value": 1,
                            "confidence": "verified",
                            "source": "POLICY",
                        },
                    }
                ]
            )
        )
        with pytest.raises(LimitsSchemaError, match="max_imagez"):
            self._load(tmp_path, data)

    def test_unknown_confidence_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table(
            p=_provider(
                defaults={
                    "max_images_per_request": {
                        "value": 1,
                        "confidence": "documented",
                        "source": "POLICY",
                    }
                }
            )
        )
        with pytest.raises(LimitsSchemaError, match="confidence"):
            self._load(tmp_path, data)

    def test_missing_source_key_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table(
            p=_provider(
                defaults={
                    "max_images_per_request": {
                        "value": 1,
                        "confidence": "verified",
                        "source": "NOPE",
                    }
                }
            )
        )
        with pytest.raises(LimitsSchemaError, match="NOPE"):
            self._load(tmp_path, data)

    def test_bad_inherit_target_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table(
            p=_provider(model_overrides=[{"pattern": "x", "inherit": "ghost"}])
        )
        with pytest.raises(LimitsSchemaError, match="ghost"):
            self._load(tmp_path, data)

    def test_invalid_regex_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table(p=_provider(model_overrides=[{"pattern": "("}]))
        with pytest.raises(LimitsSchemaError, match="pattern"):
            self._load(tmp_path, data)

    def test_unsupported_schema_version_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table()
        data["_meta"]["schema_version"] = 2
        with pytest.raises(LimitsSchemaError, match="schema_version"):
            self._load(tmp_path, data)

    def test_documentation_only_keys_are_tolerated(self, tmp_path: Path) -> None:
        data = _minimal_table(
            p=_provider(
                litellm_model_prefix="x/",
                routing_note="…",
                governed_by="…",
                published_limit="none",
                vision_models={"families": {}},
                source="POLICY",
                model_overrides=[{"pattern": "y", "description": "d", "note": "n"}],
            )
        )
        data["_meta"]["anything"] = "goes"
        data["default"]["applies_to"] = "…"
        data["default"]["rationale"] = "…"
        assert "p" in self._load(tmp_path, data).providers


class TestOverrideFile:
    def test_env_override_replaces_a_provider_wholesale(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        override = _minimal_table(
            azure=_provider(
                adapter="azure_openai",
                display_name="Azure (patched)",
                defaults={
                    "max_images_per_request": {
                        "value": 10,
                        "confidence": "unverified",
                        "source": "POLICY",
                    }
                },
            )
        )
        del override["default"]  # defaults untouched
        path = tmp_path / "override.json"
        path.write_text(json.dumps(override))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))

        table = get_limits_table()
        limits = resolve_image_limits("azure", "azure/my-dep", table=table)
        assert limits.max_images_per_request.value == 10
        assert limits.provider_label == "Azure (patched)"
        assert table.providers["azure"].layer == "override"
        # Untouched providers keep the shipped data and layer.
        assert table.providers["openai"].layer == "shipped"
        assert (
            resolve_image_limits(
                "openai", "openai/gpt-4o", table=table
            ).max_images_per_request.value
            == 1500
        )

    def test_env_override_can_replace_the_default_block(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        override = _minimal_table()
        override["default"]["max_images_per_request"]["value"] = 5
        path = tmp_path / "override.json"
        path.write_text(json.dumps(override))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))

        limits = resolve_image_limits(
            "ollama", "ollama_chat/llava", table=get_limits_table()
        )
        assert limits.max_images_per_request.value == 5

    def test_malformed_override_is_logged_and_ignored(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "override.json"
        path.write_text("{not json")
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))

        table = get_limits_table()
        assert table.providers["azure"].layer == "shipped"
        assert any("override" in rec.message.lower() for rec in caplog.records)

    def test_missing_override_file_is_logged_and_ignored(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(tmp_path / "nope.json"))
        assert get_limits_table().providers["azure"].layer == "shipped"

    def test_table_is_cached_per_process(self) -> None:
        assert get_limits_table() is get_limits_table()


class TestInheritanceIsOneLevel:
    """``inherit`` loops passed loading and recursed forever at lookup."""

    def _write(self, tmp_path: Path, data: dict) -> Path:
        path = tmp_path / "limits.json"
        path.write_text(json.dumps(data))
        return path

    def test_self_inheritance_is_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table(
            openai=_provider(
                model_overrides=[{"pattern": ".*", "inherit": "openai"}]
            )
        )
        with pytest.raises(LimitsSchemaError, match="inherits itself"):
            load_limits_table(self._write(tmp_path, data))

    def test_chained_inheritance_is_rejected(self, tmp_path: Path) -> None:
        data = _minimal_table(
            a=_provider(model_overrides=[{"pattern": "x", "inherit": "b"}]),
            b=_provider(model_overrides=[{"pattern": "y", "inherit": "c"}]),
            c=_provider(),
        )
        with pytest.raises(LimitsSchemaError, match="only one level"):
            load_limits_table(self._write(tmp_path, data))

    def test_override_creating_a_cross_layer_cycle_is_ignored(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        # The shipped openrouter inherits anthropic; an override making
        # anthropic inherit openrouter closes the loop across layers.
        bundled = json.loads(BUNDLED.read_text())
        anthropic = dict(bundled["providers"]["anthropic"])
        anthropic["model_overrides"] = [
            {"pattern": ".*", "inherit": "openrouter"},
            *anthropic.get("model_overrides", []),
        ]
        override = {"_meta": {"schema_version": 1}, "providers": {"anthropic": anthropic}}
        path = tmp_path / "override.json"
        path.write_text(json.dumps(override))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))

        table = get_limits_table()
        assert table.providers["anthropic"].layer == "shipped"
        limits = resolve_image_limits(
            "openrouter", "openrouter/anthropic/claude-haiku-4-5", table=table
        )
        assert limits.max_images_per_request.value is not None


class TestMalformedOverrideFallsBack:
    """A malformed override must be logged and ignored, never raise past the
    fallback (Greptile #2341: AttributeError / TypeError escaped).
    """

    @pytest.mark.parametrize(
        "override",
        [
            {"sources": [{"url": "x"}]},
            {"sources": {"X": "not-an-object"}},
            {"providers": ["openai"]},
            "not-an-object",
        ],
    )
    def test_shipped_table_is_kept(
        self, tmp_path: Path, monkeypatch: MonkeyPatch, override: object
    ) -> None:
        path = tmp_path / "override.json"
        path.write_text(json.dumps(override))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))

        table = get_limits_table()
        assert all(p.layer == "shipped" for p in table.providers.values())
        assert resolve_image_limits("azure", "azure/my-dep", table=table)

    def test_invalid_json_is_ignored(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        path = tmp_path / "override.json"
        path.write_text("{not json")
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))
        table = get_limits_table()
        assert all(p.layer == "shipped" for p in table.providers.values())
