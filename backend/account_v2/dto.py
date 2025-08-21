from dataclasses import dataclass
from typing import Any


@dataclass
class MemberData:
    user_id: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    role: list[str] | None = None
    organization_id: str | None = None


@dataclass
class OrganizationData:
    id: str
    display_name: str
    name: str


@dataclass
class CallbackData:
    user_id: str
    email: str
    token: Any


@dataclass
class OrganizationSignupRequestBody:
    name: str
    display_name: str
    organization_id: str


@dataclass
class OrganizationSignupResponse:
    name: str
    display_name: str
    organization_id: str
    created_at: str


@dataclass
class UserInfo:
    email: str
    user_id: str
    id: str | None = None
    name: str | None = None
    display_name: str | None = None
    family_name: str | None = None
    picture: str | None = None


@dataclass
class UserSessionInfo:
    id: str
    user_id: str
    email: str
    organization_id: str
    user: UserInfo
    role: str
    provider: str
    is_staff: bool = False

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "UserSessionInfo":
        return UserSessionInfo(
            id=data["id"],
            user_id=data["user_id"],
            email=data["email"],
            organization_id=data["organization_id"],
            role=data["role"],
            provider=data["provider"],
            is_staff=data.get("is_staff", False),
        )

    def to_dict(self) -> Any:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.email,
            "organization_id": self.organization_id,
            "role": self.role,
            "is_staff": self.is_staff,
        }


@dataclass
class GetUserReposne:
    user: UserInfo
    organizations: list[OrganizationData]


@dataclass
class ResetUserPasswordDto:
    status: bool
    message: str


@dataclass
class UserInviteResponse:
    email: str
    status: str
    message: str | None = None


@dataclass
class UserRoleData:
    name: str
    id: str | None = None
    description: str | None = None


@dataclass
class MemberInvitation:
    """Represents an invitation to join an organization.

    Attributes:
        id (str): The unique identifier for the invitation.
        email (str): The user email.
        roles (List[str]): The roles assigned to the invitee.
        created_at (Optional[str]): The timestamp when the invitation
            was created.
        expires_at (Optional[str]): The timestamp when the invitation expires.
    """

    id: str
    email: str
    roles: list[str]
    created_at: str | None = None
    expires_at: str | None = None


@dataclass
class UserOrganizationRole:
    user_id: str
    role: UserRoleData
    organization_id: str
