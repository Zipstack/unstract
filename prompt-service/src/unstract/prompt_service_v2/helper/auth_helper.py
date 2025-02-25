from typing import Any, Optional

from flask import Request, current_app, request
from unstract.prompt_service_v2.constants import DBTableV2
from unstract.prompt_service_v2.extensions import db
from unstract.prompt_service_v2.utils.db_utils import DBUtils
from unstract.prompt_service_v2.utils.env_loader import get_env_or_die

DB_SCHEMA = get_env_or_die("DB_SCHEMA", "unstract")


class AuthHelper:

    @staticmethod
    def validate_bearer_token(token: Optional[str]) -> bool:
        try:
            if token is None:
                current_app.logger.error("Authentication failed. Empty bearer token")
                return False

            platform_key_table = f'"{DB_SCHEMA}".{DBTableV2.PLATFORM_KEY}'

            query = f"SELECT * FROM {platform_key_table} WHERE key = '{token}'"
            cursor = db.execute_sql(query)
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
        platform_key_table = DBTableV2.PLATFORM_KEY
        organization_table = DBTableV2.ORGANIZATION

        query = f"SELECT organization_id FROM {platform_key_table} WHERE key='{token}'"
        organization = DBUtils.execute_query(query)
        query_org = (
            f"SELECT schema_name FROM {organization_table} WHERE id='{organization}'"
        )
        schema_name: str = DBUtils.execute_query(query_org)
        return schema_name

    @staticmethod
    def auth_required(func: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = AuthHelper.get_token_from_auth_header(request)
            # Check if bearer token exists and validate it
            if not token or not AuthHelper.validate_bearer_token(token):
                return "Unauthorized", 401
            request.token = token
            return func(*args, **kwargs)

        return wrapper
