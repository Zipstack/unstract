from account.constants import Common
from django.http import HttpRequest


class UserSessionUtils:
    @staticmethod
    def get_organization_id(request: HttpRequest) -> str:
        return request.session.get("organization", Common.PUBLIC_SCHEMA_NAME)

    @staticmethod
    def set_organization_id(request: HttpRequest, organization_id: str) -> None:
        request.session["organization"] = organization_id
