from account_v2.models import Organization
from django.db.utils import ProgrammingError

from utils.constants import Account
from utils.local_context import StateStore

# The cached organization is dropped whenever the organization id is set or
# cleared, so every request or task resolves it afresh at most once.
StateStore.register_derived_key(Account.ORGANIZATION_ID, Account.ORGANIZATION_CACHE)


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
        # Skip the query so this stays evaluable on a DB-less/unmigrated setup.
        if not organization_id:
            return None
        # Every org-scoped queryset calls this, so resolve once per request or
        # task. The cached entry carries the id it was resolved for and is used
        # only while that id is still current: it can never return another
        # organization than the lookup below would.
        cached = StateStore.get(Account.ORGANIZATION_CACHE)
        if isinstance(cached, tuple) and cached[0] == organization_id:
            cached_organization: Organization = cached[1]
            # A deleted instance has no pk; fall through to the lookup.
            if cached_organization.pk is not None:
                return cached_organization
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
        # Misses above are not cached, so they behave exactly as before.
        StateStore.set(Account.ORGANIZATION_CACHE, (organization_id, organization))
        return organization

    @staticmethod
    def cache_organization(organization: Organization) -> None:
        """Seed the cache with an organization the caller already loaded.

        Call after setting the organization id, since setting it drops the
        cache. Ignored unless ``organization`` is the current organization.
        """
        organization_id = StateStore.get(Account.ORGANIZATION_ID)
        if organization_id and organization.organization_id == organization_id:
            StateStore.set(Account.ORGANIZATION_CACHE, (organization_id, organization))

    @staticmethod
    def clear_organization_cache() -> None:
        if StateStore.get(Account.ORGANIZATION_CACHE) is not None:
            StateStore.clear(Account.ORGANIZATION_CACHE)
