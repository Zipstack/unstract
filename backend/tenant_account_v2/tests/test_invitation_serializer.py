from account_v2.dto import MemberInvitation

from tenant_account_v2.serializer import ListInvitationsResponseSerializer


class TestListInvitationsResponseSerializer:
    def test_serializes_all_fields(self):
        invitation = MemberInvitation(
            id="inv_1",
            email="alice@example.com",
            roles=["unstract_admin", "unstract_user"],
            created_at="2026-05-01T10:00:00Z",
            expires_at="2026-05-08T10:00:00Z",
            inviter_name="Bob Smith",
        )

        data = ListInvitationsResponseSerializer(invitation).data

        assert data["id"] == "inv_1"
        assert data["email"] == "alice@example.com"
        assert data["roles"] == ["unstract_admin", "unstract_user"]
        assert data["created_at"] == "2026-05-01T10:00:00Z"
        assert data["expires_at"] == "2026-05-08T10:00:00Z"
        assert data["inviter_name"] == "Bob Smith"

    def test_inviter_name_optional(self):
        invitation = MemberInvitation(
            id="inv_2",
            email="carol@example.com",
            roles=[],
            created_at="2026-05-01T10:00:00Z",
            expires_at="2026-05-08T10:00:00Z",
        )

        data = ListInvitationsResponseSerializer(invitation).data

        assert data["roles"] == []
        assert data["inviter_name"] is None
