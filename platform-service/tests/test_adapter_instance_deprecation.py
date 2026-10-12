"""A deprecated adapter still wired into a project must fail cleanly (UN-2896).

Once the V1 adapter leaves the SDK registry, resolving one would blow up deep
in the SDK and surface as a 500. The `is_available` column is checked first so
the caller gets a 400 naming the adapter instead.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from unstract.core.flask.exceptions import APIError
from unstract.platform_service.helper.adapter_instance import (
    AdapterInstanceRequestHelper,
)

COLUMNS = [
    "id",
    "adapter_id",
    "adapter_name",
    "adapter_type",
    "adapter_metadata_b",
    "is_available",
]


class _FakeCursor:
    def __init__(self, row):
        self._row = row
        self.description = [(name,) for name in COLUMNS]

    def fetchone(self):
        return self._row


@contextmanager
def _cursor_yielding(row):
    yield _FakeCursor(row)


def _fetch(row):
    with patch(
        "unstract.platform_service.helper.adapter_instance.safe_cursor",
        return_value=_cursor_yielding(row),
    ):
        return AdapterInstanceRequestHelper.get_adapter_instance_from_db(
            organization_id="org-1",
            adapter_instance_id="ad-1",
            organization_uid=1,
        )


def test_deprecated_adapter_is_refused_with_a_client_error():
    row = ("ad-1", "llmwhisperer|v1", "my-whisperer", "X2TEXT", b"", False)

    with pytest.raises(APIError) as exc:
        _fetch(row)

    # 400, not a 500 from the SDK failing to resolve an unregistered adapter.
    assert exc.value.code == 400
    # names the adapter so the user can find what to reconfigure
    assert "my-whisperer" in exc.value.message


def test_available_adapter_resolves_without_the_availability_column():
    row = ("ad-1", "openai|good", "my-openai", "LLM", b"", True)

    data = _fetch(row)

    assert data["adapter_id"] == "openai|good"
    # popped, so it never reaches the SDK's adapter metadata
    assert "is_available" not in data


def test_missing_adapter_is_a_404():
    with pytest.raises(APIError) as exc:
        _fetch(None)

    assert exc.value.code == 404
