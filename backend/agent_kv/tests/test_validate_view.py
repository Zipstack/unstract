import json
import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from rest_framework.test import APIRequestFactory  # noqa: E402

from agent_kv import execution_views as ev  # noqa: E402
from agent_kv.exceptions import RateLimited  # noqa: E402
from agent_kv.models import AgentKVKey  # noqa: E402
from unstract.agent_kv_schema.compile import SchemaError, compile_schema  # noqa: E402


def _authed(method="post", path="/agent-kv/validate", data=None):
    if data is None:
        data = {}
    req = getattr(APIRequestFactory(), method)(
        path,
        json.dumps(data) if data else "",
        content_type="application/json",
    )
    req.META["HTTP_AUTHORIZATION"] = "Bearer 123e4567-e89b-12d3-a456-426614174001"
    return req


# ---------------------------------------------------------------------------
# (1) Valid schema -> returns valid:true with correct counts
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVKey, "objects")
def test_validate_valid_schema_returns_counts(m_keys):
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    schema = {
        "quotation_number": {"description": "The quote number", "required": True},
        "customer": {"name": {"description": "Bill-to name"}},
        "line_items": {
            "description": "One row per line",
            "_key": "sku",
            "_array": {
                "sku": {"description": "SKU"},
                "total": {"description": "Line total", "format": "currency"},
            },
        },
        "_constraints": ["count('line_items') >= 1"],
    }
    req = _authed(data={"keys": schema})

    resp = ev.ValidateView.as_view()(req)

    assert resp.status_code == 200
    assert resp.data["valid"] is True
    assert "leaves" in resp.data
    assert "arrays" in resp.data
    assert "constraints" in resp.data
    assert isinstance(resp.data["leaves"], int)
    assert isinstance(resp.data["arrays"], int)
    assert isinstance(resp.data["constraints"], int)


# ---------------------------------------------------------------------------
# (2) Invalid schema -> returns valid:false with error message verbatim
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVKey, "objects")
def test_validate_invalid_schema_returns_error(m_keys):
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    # Pass a non-dict as top-level schema
    req = _authed(data={"keys": "not a dict"})

    resp = ev.ValidateView.as_view()(req)

    assert resp.status_code == 200
    assert resp.data["valid"] is False
    assert "error" in resp.data
    assert resp.data["error"] == "Top-level key schema must be a JSON object"


# ---------------------------------------------------------------------------
# (3) No key (no Authorization header) -> 403 Forbidden
# ---------------------------------------------------------------------------
def test_validate_no_key_returns_403():
    req = APIRequestFactory().post("/agent-kv/validate", data={})
    resp = ev.ValidateView.as_view()(req)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# (4) Over rate limit -> 429
# ---------------------------------------------------------------------------
@mock.patch("agent_kv.execution_views.check_key_rate", return_value=False)
@mock.patch.object(AgentKVKey, "objects")
def test_validate_over_rate_limit_returns_429(m_keys, m_check_rate):
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    key = AgentKVKey(id=uuid.uuid4(), name="k", is_active=True)
    m_keys.get.return_value = key
    req = _authed(data={"keys": {}})

    resp = ev.ValidateView.as_view()(req)

    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# (5) Missing 'keys' in request body -> 400
# ---------------------------------------------------------------------------
@mock.patch.object(AgentKVKey, "objects")
def test_validate_missing_keys_returns_400(m_keys):
    m_keys.get.return_value = AgentKVKey(name="k", is_active=True)
    req = _authed(data={})

    resp = ev.ValidateView.as_view()(req)

    assert resp.status_code == 400
    assert resp.data["detail"] == "body must include 'keys'"
