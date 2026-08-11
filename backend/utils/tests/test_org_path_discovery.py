"""Guards for the pinned organization FK paths.

These paths decide how every org-scoped queryset is filtered, at both the
manager layer (OrgAwareManager) and the view layer (OrganizationFilterBackend).
A path that changes silently is a cross-tenant leak or silent row loss, so both
properties are asserted here rather than left to review.

No DB access — path discovery walks the model metadata only.
"""

import pytest
from django.apps import apps
from utils.models.org_path_discovery import (
    ORG_PATH_OVERRIDES,
    _discover_org_path,
    get_org_path,
)

PINS = sorted(ORG_PATH_OVERRIDES.items())

# Nullable hops accepted as pre-existing behaviour, not introduced here.
# Rows with a NULL value on these FKs are excluded from every org-scoped
# query. Anything not listed must be non-nullable.
#
# The terminal `organization` FK is on this list for every pin:
# DefaultOrganizationMixin declares it null=True, and save() backfills it from
# UserContext, which is None outside a request. So a CustomTool or
# AdapterInstance created by a management command, data migration, Celery task
# or shell persists with organization_id NULL. Those rows are already invisible
# to their own model's default manager, so the pins do not make them any less
# visible — but the hop is nullable and the assertion below must say so rather
# than skip it.
KNOWN_NULLABLE_HOPS = {
    ("prompt_studio_v2.ToolStudioPrompt", "tool_id"),
    ("prompt_studio_document_manager_v2.DocumentManager", "organization"),
    ("prompt_studio_index_manager_v2.IndexManager", "organization"),
    ("prompt_studio_output_manager_v2.PromptStudioOutputManager", "organization"),
    ("prompt_studio_v2.ToolStudioPrompt", "organization"),
    ("prompt_profile_manager_v2.ProfileManager", "organization"),
}


@pytest.mark.parametrize("label,expected", PINS)
def test_pin_is_returned(label, expected):
    """get_org_path serves the pin, bypassing BFS."""
    assert get_org_path(apps.get_model(label)) == expected


@pytest.mark.parametrize("label,expected", PINS)
def test_pin_matches_discovery(label, expected):
    """The pin still agrees with what BFS would pick.

    Fails when a field reorder or a new FK changes the shortest path. That is
    the signal to re-derive the pin deliberately, not to update this constant
    to make CI green.
    """
    assert _discover_org_path(apps.get_model(label)) == expected


@pytest.mark.parametrize("label,expected", PINS)
def test_pin_traverses_only_non_nullable_fks(label, expected):
    """Every hop on the pin must be non-nullable, or listed as a known exception.

    Django turns a positive filter over a nullable FK into an INNER JOIN, which
    drops rows whose FK is NULL. On an org filter that is invisible data loss.

    The terminal `organization` hop is checked too, not skipped: it is the one
    that is nullable on every pin, so excluding it would make this assertion
    pass while proving nothing about the join that matters most.
    """
    model = apps.get_model(label)
    hops = expected.split("__")

    for hop in hops:
        field = model._meta.get_field(hop)
        assert not field.null or (label, hop) in KNOWN_NULLABLE_HOPS, (
            f"{model._meta.label}.{hop} is nullable: this pin drops every row "
            f"with a NULL {hop}. Pick a non-nullable path or add it to "
            f"KNOWN_NULLABLE_HOPS with a reason."
        )
        model = field.related_model

    # The walk must have landed on Organization, not merely survived.
    assert model._meta.label == "account_v2.Organization"
