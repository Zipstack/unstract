from dataclasses import dataclass
from typing import Any


@dataclass
class ResetUserPasswordDto:
    status: bool
    message: str


@dataclass
class UserInfo:
    id: str
    name: str
    email: str
    display_name: str | None = None
    family_name: str | None = None
    picture: str | None = None


@dataclass
class User:
    id: str
    user_id: str
    first_name: str
    username: str
    email: str


@dataclass
class TokenData:
    user_id: str
    email: str
    token: Any


@dataclass
class AuthOrganization:
    id: str
    display_name: str
    name: str
