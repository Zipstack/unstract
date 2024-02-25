from typing import Optional

from tenant_account.models import OrganizationMember


class OrganizationMemberService:
    def __init__(self) -> None:
        pass

    def get_user_by_email(self, email: str) -> Optional[OrganizationMember]:
        try:
            return OrganizationMember.objects.get(user__email=email)  # type: ignore
        except OrganizationMember.DoesNotExist:
            return None

    def get_user_by_user_id(self, user_id: str) -> Optional[OrganizationMember]:
        try:
            return OrganizationMember.objects.get(user__user_id=user_id)  # type: ignore
        except OrganizationMember.DoesNotExist:
            return None

    def get_user_by_id(self, id: str) -> Optional[OrganizationMember]:
        try:
            return OrganizationMember.objects.get(user=id)  # type: ignore
        except OrganizationMember.DoesNotExist:
            return None
