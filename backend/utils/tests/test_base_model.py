"""Tests for BaseModelQuerySet auto-injection of modified_at.

Django's ``auto_now=True`` only fires on ``Model.save()``, so
``QuerySet.update()`` and ``QuerySet.bulk_update()`` silently skip the
``modified_at`` bump. ``BaseModelQuerySet`` patches both paths to mirror
``auto_now`` semantics. These tests exercise the override logic directly
without needing a DB round-trip.
"""

import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.dev")
django.setup()

from django.db import models  # noqa: E402

from utils.models.base_model import BaseModelQuerySet  # noqa: E402


class _CapturingQuerySet(BaseModelQuerySet):
    """Bypass ``models.QuerySet.__init__`` so we can call the overrides directly."""

    def __new__(cls):
        return object.__new__(cls)

    def __init__(self):
        pass


class TestBaseModelQuerySetUpdate:
    def test_update_injects_modified_at_when_missing(self):
        qs = _CapturingQuerySet()
        captured = {}

        def fake_super_update(self, **kwargs):
            captured.update(kwargs)
            return 1

        with patch.object(models.QuerySet, "update", fake_super_update):
            qs.update(status="done")

        assert "modified_at" in captured
        assert isinstance(captured["modified_at"], datetime)
        assert captured["status"] == "done"

    def test_update_preserves_explicit_modified_at(self):
        qs = _CapturingQuerySet()
        explicit = datetime(2020, 1, 1)
        captured = {}

        def fake_super_update(self, **kwargs):
            captured.update(kwargs)
            return 1

        with patch.object(models.QuerySet, "update", fake_super_update):
            qs.update(status="done", modified_at=explicit)

        assert captured["modified_at"] is explicit


class TestBaseModelQuerySetBulkUpdate:
    def test_bulk_update_appends_modified_at_and_sets_on_objs(self):
        qs = _CapturingQuerySet()
        objs = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        captured = {}

        def fake_super_bulk(self, objs, fields, *args, **kwargs):
            captured["objs"] = list(objs)
            captured["fields"] = list(fields)
            return len(objs)

        with patch.object(models.QuerySet, "bulk_update", fake_super_bulk):
            qs.bulk_update(objs, ["status"])

        assert "modified_at" in captured["fields"]
        assert "status" in captured["fields"]
        assert all(isinstance(obj.modified_at, datetime) for obj in objs)
        # All objs share the same timestamp from a single timezone.now() call.
        assert objs[0].modified_at == objs[1].modified_at

    def test_bulk_update_respects_explicit_modified_at_in_fields(self):
        qs = _CapturingQuerySet()
        preset = datetime(2020, 1, 1)
        objs = [SimpleNamespace(id=1, modified_at=preset)]
        captured = {}

        def fake_super_bulk(self, objs, fields, *args, **kwargs):
            captured["fields"] = list(fields)
            return len(objs)

        with patch.object(models.QuerySet, "bulk_update", fake_super_bulk):
            qs.bulk_update(objs, ["status", "modified_at"])

        # Caller opted in explicitly — do not overwrite their timestamp.
        assert objs[0].modified_at is preset
        assert captured["fields"].count("modified_at") == 1
