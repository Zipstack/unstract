"""Unit tests for LLMWhisperer v2 adapter constants.

Covers the image OutputModes value and the env-var-backed page-store retry
budget.
"""

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

    def test_default_is_three(self) -> None:
        # Deliberately no importlib.reload: reloading the constants module
        # rebinds the WhispererDefaults *class object* while helper.py keeps a
        # direct name binding to the original — which silently turns other
        # suites' ``monkeypatch.setattr(WhispererDefaults, ...)`` into no-ops
        # (and, being order-dependent, is invisible until the split changes).
        # The value is read from the env at import; with the var unset (the
        # test environment) it is the default 3.
        assert c.WhispererDefaults.PAGE_STORE_MAX_RETRIES == 3
        assert isinstance(c.WhispererDefaults.PAGE_STORE_MAX_RETRIES, int)
