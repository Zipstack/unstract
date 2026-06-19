"""DRF 3.15 org-uniqueness regression guard.

DRF 3.15 derives ``required=True`` and ``UniqueTogetherValidator``s from a
model's multi-field ``UniqueConstraint``s. ``AdapterInstance`` has an
org-scoped constraint (``adapter_name``, ``adapter_type``, ``organization``),
where ``organization`` is set server-side and never sent by clients. Without
``DropServerSetUniquenessMixin``, the serializer marks ``organization`` as
required and every create 400s. These tests pin that behaviour; no test
database is required (serializer field/validator setup only).
"""

from __future__ import annotations

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from adapter_processor_v2.serializers import AdapterInstanceSerializer  # noqa: E402
from utils.serializer.org_uniqueness import (  # noqa: E402
    SERVER_SET_UNIQUENESS_FIELDS,
)


def test_organization_not_required_on_create_serializer():
    serializer = AdapterInstanceSerializer()
    assert serializer.fields["organization"].required is False


def test_server_set_fields_absent_from_uniqueness_required_kwargs():
    serializer = AdapterInstanceSerializer()
    field_names = list(serializer.fields)
    declared_fields = serializer._declared_fields
    extra_kwargs, _hidden = serializer.get_uniqueness_extra_kwargs(
        field_names, declared_fields, {}
    )
    required_fields = {
        name for name, kwargs in extra_kwargs.items() if kwargs.get("required")
    }
    assert not (required_fields & SERVER_SET_UNIQUENESS_FIELDS)


def test_no_unique_together_validator_over_server_set_fields():
    serializer = AdapterInstanceSerializer()
    for validator in serializer.get_unique_together_validators():
        assert not (set(validator.fields) & SERVER_SET_UNIQUENESS_FIELDS)
