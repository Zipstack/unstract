"""BaseTool.__init__ reports a storage-initialisation failure as an SdkError.

The error must carry the original exception, not be a TypeError from passing
logging kwargs to stream_error_and_exit.
"""

from pathlib import Path
from typing import Any

import pytest
from unstract.sdk1.constants import ToolEnv
from unstract.sdk1.exceptions import FileStorageError, SdkError
from unstract.sdk1.tool import base as base_module
from unstract.sdk1.tool.base import BaseTool


class _Tool(BaseTool):
    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        pass

    def run(self, settings: dict[str, Any], input_file: str, output_dir: str) -> None:
        pass


def test_storage_init_failure_raises_sdk_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ToolEnv.WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS, "{}")
    monkeypatch.setenv(ToolEnv.EXECUTION_DATA_DIR, str(tmp_path))
    monkeypatch.delenv(ToolEnv.EXECUTION_BY_TOOL, raising=False)
    for name in ("properties", "spec", "variables"):
        monkeypatch.setattr(base_module.ToolConfigHelper, name, staticmethod(dict))
    cause = FileStorageError("bad credentials")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise cause

    monkeypatch.setattr(base_module.EnvHelper, "get_storage", _raise)

    with pytest.raises(SdkError) as exc_info:
        _Tool()

    assert exc_info.value.actual_err is cause
    assert "bad credentials" in str(exc_info.value)
