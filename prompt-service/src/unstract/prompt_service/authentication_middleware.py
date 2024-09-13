from typing import Any, Optional

from flask import Request, current_app
from unstract.prompt_service import be_db, db_context
from unstract.prompt_service.constants import DBTableV2, FeatureFlag

from unstract.flags.feature_flag import check_feature_flag_status


class AuthenticationMiddleware:

    @staticmethod
    def validate_bearer_token(token: Optional[str]) -> bool:
        try:
            if token is None:
                current_app.logger.error("Authentication failed. Empty bearer token")
                return False

            if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
                platform_key_table = DBTableV2.PLATFORM_KEY
            else:
                platform_key_table = "account_platformkey"

            query = f"SELECT * FROM {platform_key_table} WHERE key = '{token}'"
            with db_context():
                cursor = be_db.execute_sql(query)
                result_row = cursor.fetchone()
                cursor.close()
            if not result_row or len(result_row) == 0:
                current_app.logger.error(
                    f"Authentication failed. bearer token not found {token}"
                )
                return False
            platform_key = str(result_row[1])
            is_active = bool(result_row[2])
            if not is_active:
                current_app.logger.error(
                    f"Token is not active. Activate \
                        before using it. token {token}"
                )
                return False
            if platform_key != token:
                current_app.logger.error(
                    f"Authentication failed. Invalid bearer token: {token}"
                )
                return False

        except Exception as e:
            current_app.logger.error(
                f"Error while validating bearer token: {e}",
                stack_info=True,
                exc_info=True,
            )
            return False
        return True

    @staticmethod
    def get_token_from_auth_header(request: Request) -> Optional[str]:
        try:
            bearer_token = request.headers.get("Authorization")
            if not bearer_token:
                return None
            token: str = bearer_token.strip().replace("Bearer ", "")
            return token
        except Exception as e:
            current_app.logger.info(f"Exception while getting token {e}")
            return None

    @staticmethod
    def get_account_from_bearer_token(token: Optional[str]) -> str:
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            platform_key_table = DBTableV2.PLATFORM_KEY
            organization_table = DBTableV2.ORGANIZATION
        else:
            platform_key_table = "account_platformkey"
            organization_table = "account_organization"

        query = f"SELECT organization_id FROM {platform_key_table} WHERE key='{token}'"
        organization = AuthenticationMiddleware.execute_query(query)
        query_org = (
            f"SELECT schema_name FROM {organization_table} WHERE id='{organization}'"
        )
        schema_name: str = AuthenticationMiddleware.execute_query(query_org)
        return schema_name

    @staticmethod
    def execute_query(query: str) -> Any:
        with db_context():
            cursor = be_db.execute_sql(query)
            result_row = cursor.fetchone()
        cursor.close()
        if not result_row or len(result_row) == 0:
            return None
        return result_row[0]
