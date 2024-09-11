from typing import Optional

from flask import Request, current_app
from peewee import PostgresqlDatabase
from unstract.prompt_service.constants import DBTableV2, FeatureFlag
from unstract.prompt_service.db_utils import DBUtils
from unstract.prompt_service.env_manager import EnvLoader

from unstract.flags.feature_flag import check_feature_flag_status

DB_SCHEMA = EnvLoader.get_env_or_die("DB_SCHEMA", "unstract_v2")


class AuthenticationMiddleware:
    be_db: PostgresqlDatabase

    @classmethod
    def validate_bearer_token(cls, token: Optional[str]) -> bool:
        try:
            if token is None:
                current_app.logger.error("Authentication failed. Empty bearer token")
                return False

            if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
                platform_key_table = f'"{DB_SCHEMA}".{DBTableV2.PLATFORM_KEY}'
            else:
                platform_key_table = "account_platformkey"

            query = f"SELECT * FROM {platform_key_table} WHERE key = '{token}'"
            cursor = cls.be_db.execute_sql(query)
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

    @classmethod
    def get_token_from_auth_header(cls, request: Request) -> Optional[str]:
        try:
            bearer_token = request.headers.get("Authorization")
            if not bearer_token:
                return None
            token: str = bearer_token.strip().replace("Bearer ", "")
            return token
        except Exception as e:
            current_app.logger.info(f"Exception while getting token {e}")
            return None

    @classmethod
    def get_account_from_bearer_token(cls, token: Optional[str]) -> str:
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            platform_key_table = DBTableV2.PLATFORM_KEY
            organization_table = DBTableV2.ORGANIZATION
        else:
            platform_key_table = "account_platformkey"
            organization_table = "account_organization"

        query = f"SELECT organization_id FROM {platform_key_table} WHERE key='{token}'"
        organization = DBUtils.execute_query(query)
        query_org = (
            f"SELECT schema_name FROM {organization_table} WHERE id='{organization}'"
        )
        schema_name: str = DBUtils.execute_query(query_org)
        return schema_name
