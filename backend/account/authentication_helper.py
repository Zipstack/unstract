from typing import Any

from account.constants import DefaultOrg
from account.dto import CallbackData, MemberData, OrganizationData
from rest_framework.request import Request


class AuthenticationHelper:
    def __init__(self) -> None:
        pass

    def get_organizations_by_user_id(self) -> list[OrganizationData]:
        organizationData: OrganizationData = OrganizationData(
            id=DefaultOrg.MOCK_ORG,
            display_name=DefaultOrg.MOCK_ORG,
            name=DefaultOrg.MOCK_ORG,
        )
        return [organizationData]

    def get_authorize_token(rself, equest: Request) -> CallbackData:
        return CallbackData(
            user_id=DefaultOrg.MOCK_USER_ID,
            email=DefaultOrg.MOCK_USER_EMAIL,
            token="",
        )

    def list_of_members_from_user_model(
        self, model_data: list[Any]
    ) -> list[MemberData]:
        members: list[MemberData] = []
        for data in model_data:
            user_id = data.user_id
            email = data.email
            name = data.username

            members.append(MemberData(user_id=user_id, email=email, name=name))

        return members
