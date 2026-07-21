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
    def get_organization() -> Organization | None:
        organization_id = StateStore.get(Account.ORGANIZATION_ID)
        # No org in context (import time, or management commands with no request):
        # skip the query so evaluating this on a DB-less/unmigrated setup can't fail.
        if not organization_id:
            return None
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
