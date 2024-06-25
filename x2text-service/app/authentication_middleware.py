from typing import Any, Optional

from app.models import be_db
from flask import Request, current_app, request


def authentication_middleware(func: Any) -> Any:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = AuthenticationMiddleware.get_token_from_auth_header(request)
        # Check if bearer token exists and validate it
        if not token or not AuthenticationMiddleware.validate_bearer_token(token):
            return "Unauthorized", 401

        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


class AuthenticationMiddleware:
    @classmethod
    def validate_bearer_token(cls, token: Optional[str]) -> bool:
        try:
            if token is None:
                current_app.logger.error("Authentication failed. Empty bearer token")
                return False

            query = f"SELECT * FROM account_platformkey WHERE key = '{token}'"
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
        query = (
            "SELECT organization_id FROM account_platformkey " f"WHERE key='{token}'"
        )
        organization = AuthenticationMiddleware.execute_query(query)
        query_org = (
            "SELECT schema_name FROM account_organization " f"WHERE id='{organization}'"
        )
        schema_name: str = AuthenticationMiddleware.execute_query(query_org)
        return schema_name

    @classmethod
    def execute_query(cls, query: str) -> Any:
        cursor = be_db.execute_sql(query)
        result_row = cursor.fetchone()
        cursor.close()
        if not result_row or len(result_row) == 0:
            return None
        return result_row[0]
