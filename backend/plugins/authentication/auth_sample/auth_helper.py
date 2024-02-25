import logging

from authlib.integrations.django_client import OAuth
from rest_framework.request import Request
from rest_framework.response import Response

from .dto import TokenData
from .exceptions import MethodNotImplemented

Logger = logging.getLogger(__name__)


class AuthHelper:
    def __init__(self) -> None:
        self.oauth = OAuth()

        self.oauth.register("auth_project_name")

    def get_authorize_token(self, request: Request) -> TokenData:
        return TokenData(
            user_id="",
            email="",
            token="",
        )

    def get_oauth_token(self) -> str:
        raise MethodNotImplemented()

    def auth_logout(self, request: Request) -> Response:
        raise MethodNotImplemented()

    def clear_custom_cookies(self, response: Response) -> None:
        raise MethodNotImplemented()

    def autho_reset_password(self, email: str) -> bool:
        raise MethodNotImplemented()
