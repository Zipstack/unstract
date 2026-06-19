"""Guard: server-managed ``organization`` stays out of writable serializer input.

``organization`` is set server-side, never sent by clients. Marking it
``editable=False`` on the model keeps DRF from exposing it as a writable
field, which in turn keeps it out of the auto-generated multi-field
uniqueness validators (DRF 3.15+) that would otherwise reject every create
with ``organization: This field is required``. No test database is required
(serializer field/validator setup only).
"""

from __future__ import annotations

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from rest_framework.validators import UniqueTogetherValidator  # noqa: E402

from adapter_processor_v2.serializers import AdapterInstanceSerializer  # noqa: E402


def test_organization_is_read_only():
    serializer = AdapterInstanceSerializer()
    assert serializer.fields["organization"].read_only is True


def test_no_uniqueness_validator_references_organization():
    serializer = AdapterInstanceSerializer()
    offending = [
        v
        for v in serializer.validators
        if isinstance(v, UniqueTogetherValidator) and "organization" in tuple(v.fields)
    ]
    assert offending == []


def test_create_payload_without_organization_validates():
    payload = {
        "adapter_id": "openai|abc",
        "adapter_name": "test-llm",
        "adapter_type": "LLM",
        "adapter_metadata": {"model": "gpt"},
    }
    serializer = AdapterInstanceSerializer(data=payload)
    serializer.is_valid()
    assert "organization" not in serializer.errors
