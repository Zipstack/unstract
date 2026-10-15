"""The role alphabets are wire contracts: pin every value.

``OrganizationMember.role`` stores these strings, the permission checks compare
against them, and the SPA matches the ``unstract_*`` ones literally
(``RequireAuth.jsx``, ``SideNavBar.jsx``, ``InviteEditUser.jsx`` and others). A
renamed value is a silent permission change, so a change here must fail a test.
"""

from account_v2.enums import UnstractRole, UserRole


def test_default_service_alphabet_is_pinned() -> None:
    assert {role.name: role.value for role in UserRole} == {
        "USER": "user",
        "ADMIN": "admin",
    }


def test_plugin_alphabet_is_pinned() -> None:
    assert {role.name: role.value for role in UnstractRole} == {
        "USER": "unstract_user",
        "ADMIN": "unstract_admin",
        "SUPERVISOR": "unstract_supervisor",
        "REVIEWER": "unstract_reviewer",
        "PLATFORM_ADMIN": "unstract_platform_admin",
    }


def test_members_compare_equal_to_their_wire_strings() -> None:
    # StrEnum: a member is usable wherever the stored string is, so call sites
    # can move from ``.value`` to the member without changing a comparison.
    assert UserRole.ADMIN == "admin"
    assert UnstractRole.ADMIN == "unstract_admin"
    assert f"{UnstractRole.REVIEWER}" == "unstract_reviewer"


def test_alphabets_are_disjoint() -> None:
    # The default service's "admin" is not an administrator under the plugins,
    # and the reverse. Overlap would make the two alphabets ambiguous.
    assert not {r.value for r in UserRole} & {r.value for r in UnstractRole}


def test_parsing_a_stored_string_returns_the_member() -> None:
    assert UnstractRole("unstract_admin") is UnstractRole.ADMIN
    assert UserRole("admin") is UserRole.ADMIN
