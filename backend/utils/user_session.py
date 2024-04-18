from typing import Optional

from django.http import HttpRequest


class UserSessionUtils:
    @staticmethod
    def get_organization_id(request: HttpRequest) -> Optional[str]:
        return request.session.get("organization")

    @staticmethod
    def set_organization_id(request: HttpRequest, organization_id: str) -> None:
        request.session["organization"] = organization_id
