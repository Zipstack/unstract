"""Unit tests for LLMWhisperer v2 adapter constants (MUNS-193).

Covers:
- UNS-732: OutputModes.IMAGE enum value.
- UNS-733: ADAPTER_LLMW_PAGE_STORE_MAX_RETRIES env-var-backed constant.
"""

import importlib

from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src import constants as c

_ENV_VAR = "ADAPTER_LLMW_PAGE_STORE_MAX_RETRIES"


class TestOutputModesImage:
    def test_image_mode_value(self) -> None:
        assert c.OutputModes.IMAGE.value == "image"

    def test_existing_modes_unchanged(self) -> None:
        assert c.OutputModes.TEXT.value == "text"
        assert c.OutputModes.LAYOUT_PRESERVING.value == "layout_preserving"


class TestPageStoreMaxRetries:
    def test_env_var_name(self) -> None:
        assert c.WhispererEnv.PAGE_STORE_MAX_RETRIES == _ENV_VAR

    def test_default_is_three(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv(_ENV_VAR, raising=False)
        reloaded = importlib.reload(c)
        try:
            assert reloaded.WhispererDefaults.PAGE_STORE_MAX_RETRIES == 3
            assert isinstance(reloaded.WhispererDefaults.PAGE_STORE_MAX_RETRIES, int)
        finally:
            importlib.reload(c)

    def test_reads_from_env(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv(_ENV_VAR, "5")
        reloaded = importlib.reload(c)
        try:
            assert reloaded.WhispererDefaults.PAGE_STORE_MAX_RETRIES == 5
        finally:
            monkeypatch.delenv(_ENV_VAR, raising=False)
            importlib.reload(c)
