"""Guard: server-managed ``organization`` stays out of writable serializer input.

``organization`` is set server-side, never sent by clients. Marking it
``editable=False`` on the model keeps DRF from exposing it as a writable
field, which in turn keeps it out of the auto-generated multi-field
uniqueness validators (DRF 3.15+) that would otherwise reject every create
with ``organization: This field is required``.

The field-level invariant is the root-cause guard: if ``organization`` stays
``editable=False`` on every org-scoped model, no serializer can re-expose it.
The adapter serializer cases additionally pin the concrete DRF-3.15 symptom.
No test database is required (model/serializer setup only).
"""

from __future__ import annotations

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from rest_framework.validators import UniqueTogetherValidator  # noqa: E402

from adapter_processor_v2.serializers import AdapterInstanceSerializer  # noqa: E402

# Every org-scoped model whose ``organization`` FK must stay non-editable:
# mixin users plus the five models that declare the FK directly.
ORG_SCOPED_MODELS = [
    ("adapter_processor_v2", "AdapterInstance"),
    ("api_v2", "APIDeployment"),
    ("api_v2", "OrganizationRateLimit"),
    ("connector_v2", "ConnectorInstance"),
    ("pipeline_v2", "Pipeline"),
    ("tags", "Tag"),
    ("workflow_v2", "Workflow"),
    ("configuration", "Configuration"),
    ("account_v2", "PlatformKey"),
    ("tenant_account_v2", "OrganizationGroup"),
    ("tenant_account_v2", "ResourceGroupShare"),
    ("notification_v2", "NotificationBuffer"),
]


@pytest.mark.parametrize("app_label,model_name", ORG_SCOPED_MODELS)
def test_organization_field_not_editable(app_label, model_name):
    field = apps.get_model(app_label, model_name)._meta.get_field("organization")
    assert field.editable is False


def test_adapter_serializer_org_read_only():
    assert AdapterInstanceSerializer().fields["organization"].read_only is True


def test_adapter_no_uniqueness_validator_references_organization():
    serializer = AdapterInstanceSerializer()
    offending = [
        v
        for v in serializer.validators
        if isinstance(v, UniqueTogetherValidator) and "organization" in tuple(v.fields)
    ]
    assert offending == []


def test_adapter_create_payload_without_organization_validates():
    payload = {
        "adapter_id": "openai|abc",
        "adapter_name": "test-llm",
        "adapter_type": "LLM",
        "adapter_metadata": {"model": "gpt"},
    }
    serializer = AdapterInstanceSerializer(data=payload)
    serializer.is_valid()
    assert "organization" not in serializer.errors
