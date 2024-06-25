from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class MemberData:
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    role: Optional[list[str]] = None
    organization_id: Optional[str] = None


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
    id: Optional[str] = None
    name: Optional[str] = None
    display_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None


@dataclass
class UserSessionInfo:
    id: str
    user_id: str
    email: str
    organization_id: str
    user: UserInfo
    role: str

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "UserSessionInfo":
        return UserSessionInfo(
            id=data["id"],
            user_id=data["user_id"],
            email=data["email"],
            organization_id=data["organization_id"],
            role=data["role"],
        )

    def to_dict(self) -> Any:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.email,
            "organization_id": self.organization_id,
            "role": self.role,
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
    message: Optional[str] = None


@dataclass
class UserRoleData:
    name: str
    id: Optional[str] = None
    description: Optional[str] = None


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
    created_at: Optional[str] = None
    expires_at: Optional[str] = None


@dataclass
class UserOrganizationRole:
    user_id: str
    role: UserRoleData
    organization_id: str
