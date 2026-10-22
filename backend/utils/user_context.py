from account_v2.models import Organization
from django.core.signals import request_finished
from django.db.utils import ProgrammingError

from utils.constants import Account
from utils.local_context import StateStore

# The cached organization is dropped whenever the organization id is set or
# cleared, so each setting of the id resolves it afresh at most once (a lookup
# that finds no row is not cached and runs again). A path that sets the id and never clears it (whitelisted paths return
# from CustomAuthMiddleware before its clear; some Celery tasks rely on a
# leftover id) gets a boundary hook instead: request_finished below,
# task_postrun in backend.celery_service.
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
    def set_organization(organization: Organization) -> None:
        """Set the organization id from a row the caller already loaded, and cache it.

        One call, in this order, so the drop that setting the id triggers can
        never land after the seed.
        """
        StateStore.set(Account.ORGANIZATION_ID, organization.organization_id)
        UserContext.cache_organization(organization)

    @staticmethod
    def get_organization() -> Organization | None:
        """Resolve the current organization, at most once per setting of the id.

        Later calls return the same instance until the id is next set or the
        cache cleared, so a write to the row through another instance is not
        reflected in it until then. Conversely, every caller shares that
        instance: an attribute changed on it and not saved is seen by later
        org-scoped code in the same request or task.
        """
        organization_id = StateStore.get(Account.ORGANIZATION_ID)
        # Skip the query so this stays evaluable on a DB-less/unmigrated setup.
        if not organization_id:
            return None
        # Every org-scoped queryset calls this. The cached entry carries the id
        # it was resolved for and is used only while that id is still current,
        # so it is never another organization than the lookup below would
        # return for the same id.
        cached = StateStore.get(Account.ORGANIZATION_CACHE)
        if isinstance(cached, tuple) and cached[0] == organization_id:
            cached_organization: Organization = cached[1]
            # ``.delete()`` on this instance sets its pk to None (a row deleted
            # through another instance is not detected); fall through to the
            # lookup.
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

        Ignored unless ``organization`` is the current organization, so it must
        run after the id is set (``set_organization`` does both, in order).
        """
        organization_id = StateStore.get(Account.ORGANIZATION_ID)
        if organization_id and organization.organization_id == organization_id:
            StateStore.set(Account.ORGANIZATION_CACHE, (organization_id, organization))

    @staticmethod
    def clear_organization_cache() -> None:
        if StateStore.get(Account.ORGANIZATION_CACHE) is not None:
            StateStore.clear(Account.ORGANIZATION_CACHE)


def _drop_cached_organization(**kwargs: object) -> None:
    """Request boundary for paths that set the organization id and never clear it.

    Whitelisted paths return from CustomAuthMiddleware before its clear, and
    the views behind them (API deployments, the OAuth callback) set the id
    themselves. Without this the cached row would stay on the gunicorn thread
    until the id is next set, and be served stale to a later request on that
    thread that relies on the leftover id.
    """
    UserContext.clear_organization_cache()


request_finished.connect(
    _drop_cached_organization,
    dispatch_uid="utils.user_context.drop_cached_organization",
)
