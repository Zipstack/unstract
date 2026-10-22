"""Which resources have access that does not depend on shares at all.

Revoking a share from such a resource removes nothing, so nobody may be told it
did. Two routes qualify and they are easy to miss because neither is a share
row: ``shared_to_org`` admits every org member, and ``is_friction_less`` is the
adapter equivalent -- ``AdapterInstance.for_user`` admits it unconditionally,
alongside the share clauses.

Pure predicate, so this runs in the rig's unit tier with no database. The
admin route is the third one and is user-level rather than resource-level, so
it lives in ``org_admin_user_ids`` and is covered by the DB tests.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tenant_account_v2.sharing_helpers import access_survives_share_changes


class TestAccessSurvivesShareChanges:
    @pytest.mark.parametrize(
        "resource, expected, why",
        [
            (SimpleNamespace(shared_to_org=True), True, "org-wide share"),
            (SimpleNamespace(is_friction_less=True), True, "frictionless adapter"),
            (
                SimpleNamespace(shared_to_org=False, is_friction_less=True),
                True,
                "frictionless without an org share still admits everyone",
            ),
            (
                SimpleNamespace(shared_to_org=True, is_friction_less=False),
                True,
                "org share without frictionless still admits everyone",
            ),
            (
                SimpleNamespace(shared_to_org=False, is_friction_less=False),
                False,
                "neither route: access really does depend on the share",
            ),
            (
                SimpleNamespace(),
                False,
                "a model carrying neither field, e.g. Workflow, is share-dependent",
            ),
        ],
    )
    def test_routes(self, resource, expected, why):
        assert access_survives_share_changes(resource) is expected, why
