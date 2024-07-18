import logging
from typing import Optional

from account_v2.models import Organization
from account_v2.subscription_loader import SubscriptionConfig, load_plugins
from django.db import IntegrityError

Logger = logging.getLogger(__name__)

subscription_loader = load_plugins()


class OrganizationService:
    def __init__(self):  # type: ignore
        pass

    @staticmethod
    def get_organization_by_org_id(org_id: str) -> Optional[Organization]:
        try:
            return Organization.objects.get(organization_id=org_id)  # type: ignore
        except Organization.DoesNotExist:
            return None

    @staticmethod
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

            for subscription_plugin in subscription_loader:
                cls = subscription_plugin[SubscriptionConfig.METADATA][
                    SubscriptionConfig.METADATA_SERVICE_CLASS
                ]
                cls.add(organization_id=organization_id)

        except IntegrityError as error:
            Logger.info(f"[Duplicate Id] Failed to create Organization Error: {error}")
            raise error
        return organization
