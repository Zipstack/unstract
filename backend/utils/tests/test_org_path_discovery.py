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
    _org_path_cache,
    get_org_path,
)

PINS = sorted(ORG_PATH_OVERRIDES.items())

# The pin set itself, as a literal. PINS is derived from the dict under test,
# so every parametrized case below disappears along with a deleted pin and the
# file stays green while losing coverage. This is the only assertion here that
# a deletion cannot take with it.
EXPECTED_PINNED_LABELS = {
    "prompt_studio_document_manager_v2.DocumentManager",
    "prompt_studio_index_manager_v2.IndexManager",
    "prompt_studio_output_manager_v2.PromptStudioOutputManager",
    "prompt_studio_v2.ToolStudioPrompt",
    "prompt_profile_manager_v2.ProfileManager",
}

# Nullable hops accepted as pre-existing behaviour, not introduced here.
# Rows with a NULL value on these FKs are excluded from every org-scoped
# query. Anything not listed must be non-nullable.
#
# Keyed by the model that *declares* the field, not by the pin it appears on —
# a hop belongs to the model the walk is standing on when it reads that name,
# and several pins share the same hop. The two terminal `organization` FKs are
# here because DefaultOrganizationMixin declares them null=True and save()
# backfills from UserContext, which is None outside a request. So a CustomTool
# or AdapterInstance created by a management command, data migration, Celery
# task or shell persists with organization_id NULL. Those rows are already
# invisible to their own model's default manager, so the pins do not make them
# any less visible — but the hop is nullable and the assertion below must say
# so rather than skip it.
KNOWN_NULLABLE_HOPS = {
    ("prompt_studio_v2.ToolStudioPrompt", "tool_id"),
    ("prompt_studio_core_v2.CustomTool", "organization"),
    ("adapter_processor_v2.AdapterInstance", "organization"),
}


def test_pin_set_is_exactly_what_is_expected():
    """A pin removed or added has to be a deliberate edit here."""
    assert set(ORG_PATH_OVERRIDES) == EXPECTED_PINNED_LABELS


@pytest.mark.parametrize("label,expected", PINS)
def test_pin_is_returned(label, expected):
    """get_org_path serves the pin."""
    assert get_org_path(apps.get_model(label)) == expected


@pytest.mark.parametrize("label,expected", PINS)
def test_pin_short_circuits_discovery(label, expected, monkeypatch):
    """...and serves it *instead of* running BFS, not merely in agreement.

    BFS independently arrives at all five pins today, so the assertion above
    holds with the short-circuit removed. Stubbing discovery to a value no pin
    has is what separates the two.
    """
    model = apps.get_model(label)
    monkeypatch.setattr(
        "utils.models.org_path_discovery._discover_org_path",
        lambda _model: "sentinel__organization",
    )
    # The memo would answer from an earlier test's real lookup and hide the
    # stub, so drop this model's entry for the duration.
    monkeypatch.delitem(_org_path_cache, model, raising=False)
    assert get_org_path(model) == expected


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
        # Owner read before the walk advances: the key has to name the model
        # that declares the field, which is what the failure message prints
        # and what the reader has to add to the set.
        owner = model._meta.label
        assert not field.null or (owner, hop) in KNOWN_NULLABLE_HOPS, (
            f"{owner}.{hop} is nullable: this pin drops every row with a NULL "
            f"{hop}. Pick a non-nullable path or add ({owner!r}, {hop!r}) to "
            f"KNOWN_NULLABLE_HOPS with a reason."
        )
        model = field.related_model

    # The walk must have landed on Organization, not merely survived.
    assert model._meta.label == "account_v2.Organization"
