"""Unit checks for the 404 detail enrichment in the DRF exception handler.

Pure-logic; uses fakes so no DB or real models are needed. Importing the
handler pulls DRF, which reads settings at import — configure a minimal
settings object when the suite hasn't already, so this runs standalone too.
"""

import django
from django.conf import settings

if not settings.configured:
    settings.configure(INSTALLED_APPS=[], DATABASES={})
    django.setup()

from middleware.exception import _enrich_not_found_detail  # noqa: E402


class _Meta:
    verbose_name = "lookup definition"


class _Model:
    _meta = _Meta


class _QuerySet:
    model = _Model


class _View:
    queryset = _QuerySet


class _Resp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self.data = data


def test_404_with_model_uses_verbose_name():
    resp = _Resp(404, {"errors": [{"code": "not_found", "detail": "Not found."}]})
    _enrich_not_found_detail(resp, {"view": _View()})
    assert resp.data["errors"][0]["detail"] == "Lookup definition not found."


def test_404_without_queryset_keeps_generic():
    resp = _Resp(404, {"errors": [{"code": "not_found", "detail": "Not found."}]})
    _enrich_not_found_detail(resp, {"view": object()})
    assert resp.data["errors"][0]["detail"] == "Not found."


def test_non_404_untouched():
    resp = _Resp(400, {"errors": [{"code": "not_found", "detail": "Not found."}]})
    _enrich_not_found_detail(resp, {"view": _View()})
    assert resp.data["errors"][0]["detail"] == "Not found."


def test_none_response_is_safe():
    _enrich_not_found_detail(None, {})


def test_non_dict_error_item_does_not_raise():
    resp = _Resp(
        404, {"errors": ["unexpected", {"code": "not_found", "detail": "Not found."}]}
    )
    _enrich_not_found_detail(resp, {"view": _View()})
    assert resp.data["errors"][1]["detail"] == "Lookup definition not found."
