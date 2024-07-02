from typing import Optional

from django.db import connection
from utils.constants import Account, FeatureFlag
from utils.local_context import StateStore

from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
    # TODO: uncomment Once v2 implemented
    # from account_v2.models import Organization
    pass
else:
    from account.models import Organization


class UserContext:
    @staticmethod
    def get_organization_identifier() -> str:
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            organization_id = StateStore.get(Account.ORGANIZATION_ID)
        else:
            organization_id = connection.tenant.schema_name
        return organization_id

    @staticmethod
    def set_organization_identifier(organization_identifier: str) -> None:
        StateStore.set(Account.ORGANIZATION_ID, organization_identifier)

    @staticmethod
    def get_organization() -> Optional[Organization]:
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            organization_id = StateStore.get(Account.ORGANIZATION_ID)
            try:
                organization: Organization = Organization.objects.get(
                    organization_id=organization_id
                )
            except Organization.DoesNotExist:
                return None
        else:
            organization: Organization = connection.tenant
        return organization
