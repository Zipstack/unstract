from dataclasses import dataclass


@dataclass
class OrganizationLoginResponse:
    name: str
    display_name: str
    organization_id: str
    created_at: str


@dataclass
class ResetUserPasswordDto:
    status: bool
    message: str
