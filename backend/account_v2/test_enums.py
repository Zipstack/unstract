"""Pin every role value: a renamed value is a silent permission change."""

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


def test_members_equal_their_stored_strings() -> None:
    # Call sites compare members with stored strings, which needs StrEnum.
    assert UserRole.ADMIN == "admin"
    assert UnstractRole.ADMIN == "unstract_admin"


def test_alphabets_are_disjoint() -> None:
    assert not set(UserRole) & set(UnstractRole)
