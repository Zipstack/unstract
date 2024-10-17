from typing import Optional

from account_v2.models import Organization
from django.db.utils import ProgrammingError
from utils.constants import Account
from utils.local_context import StateStore


class UserContext:
    @staticmethod
    def get_organization_identifier() -> str:
        organization_id = StateStore.get(Account.ORGANIZATION_ID)
        return organization_id

    @staticmethod
    def set_organization_identifier(organization_identifier: str) -> None:
        StateStore.set(Account.ORGANIZATION_ID, organization_identifier)

    @staticmethod
    def get_organization() -> Optional[Organization]:
        organization_id = StateStore.get(Account.ORGANIZATION_ID)
        try:
            organization: Organization = Organization.objects.get(
                organization_id=organization_id
            )
        except Organization.DoesNotExist:
            return None
        except ProgrammingError:
            # Handle cases where the database schema might not be fully set up,
            # especially during the execution of management commands
            # other than runserver
            return None
        return organization
