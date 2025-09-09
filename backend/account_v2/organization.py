import logging

from django.db import IntegrityError
from utils.db_retry import db_retry

from account_v2.models import Organization

Logger = logging.getLogger(__name__)


class OrganizationService:
    def __init__(self):  # type: ignore
        pass

    @staticmethod
    @db_retry()  # Add retry for connection drops during organization lookup
    def get_organization_by_org_id(org_id: str) -> Organization | None:
        try:
            return Organization.objects.get(organization_id=org_id)  # type: ignore
        except Organization.DoesNotExist:
            return None

    @staticmethod
    @db_retry()  # Add retry for connection drops during organization creation
    def create_organization(
        name: str, display_name: str, organization_id: str
    ) -> Organization:
        try:
            organization: Organization = Organization(
                name=name,
                display_name=display_name,
                organization_id=organization_id,
            )
            organization.save()
        except IntegrityError as error:
            Logger.info(f"[Duplicate Id] Failed to create Organization Error: {error}")
            raise error
        return organization
