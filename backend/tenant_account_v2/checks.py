"""System checks for the group-sharing resource registry (UN-2977).

``SHAREABLE_RESOURCES`` descriptors are free strings resolved lazily via
``apps.get_model`` + ``values_list(id_field, name_field)``, so a typo otherwise
surfaces only as a runtime ``FieldError`` on the path touching that resource.
This check validates every installed descriptor at ``manage.py check`` / CI /
boot, catching drift early (e.g. the ``6a5493dc`` field-name fix).
"""

from typing import Any

from django.apps import apps
from django.core.checks import Error, register
from django.core.exceptions import FieldDoesNotExist

from tenant_account_v2.shareable_resources import SHAREABLE_RESOURCES


@register()
def check_shareable_resources_registry(app_configs: Any, **kwargs: Any) -> list[Error]:
    """Verify each registered shareable resource resolves and its fields exist."""
    errors: list[Error] = []
    for resource in SHAREABLE_RESOURCES:
        try:
            model = apps.get_model(resource.app_label, resource.model_name)
        except LookupError:
            # App not installed in this deployment (e.g. cloud-only
            # agentic_studio_v1 in pure OSS). Not a drift error.
            continue
        for attr in ("id_field", "name_field"):
            field_name = getattr(resource, attr)
            try:
                model._meta.get_field(field_name)
            except FieldDoesNotExist:
                errors.append(
                    Error(
                        f"ShareableResource '{resource.kind}' declares "
                        f"{attr}='{field_name}', which is not a field on "
                        f"{resource.app_label}.{resource.model_name}.",
                        hint="Fix the field name in SHAREABLE_RESOURCES.",
                        id="tenant_account_v2.E001",
                    )
                )
    return errors
