from typing import Any

from flask import Request, current_app, request

from app.constants import DBTable
from app.env import Env
from app.models import be_db


def authentication_middleware(func: Any) -> Any:
    """Decorator to enforce bearer token authentication on flask routes."""

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
    def validate_bearer_token(cls, token: str | None) -> bool:
        """Validate the provided bearer token against the database."""
        try:
            if token is None:
                current_app.logger.error("Authentication failed. Empty bearer token")
                return False
            platform_key_table = f'"{Env.DB_SCHEMA}".{DBTable.PLATFORM_KEY}'
            query = f"SELECT * FROM {platform_key_table} WHERE key = %s"
            cursor = be_db.execute_sql(query, (token,))
            result_row = cursor.fetchone()
            cursor.close()
            if not result_row or len(result_row) == 0:
                current_app.logger.error("Authentication failed. bearer token not found")
                return False
            platform_key = str(result_row[1])
            is_active = bool(result_row[2])
            if not is_active:
                current_app.logger.error("Token is not active. Activate before using it.")
                return False
            if platform_key != token:
                current_app.logger.error("Authentication failed. Invalid bearer token")
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
    def get_token_from_auth_header(cls, request: Request) -> str | None:
        """Extract the bearer token from the Authorization header."""
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
    def get_organization_from_bearer_token(cls, token: str) -> tuple[int | None, str]:
        """Retrieve organization ID and identifier using a bearer token.

        Args:
            token (str): The bearer token (platform key).

        Returns:
            tuple[int, str]: organization uid and organization identifier
        """
        platform_key_table = f'"{Env.DB_SCHEMA}".{DBTable.PLATFORM_KEY}'
        organization_table = f'"{Env.DB_SCHEMA}".{DBTable.ORGANIZATION}'

        organization_uid: int | None = cls.execute_query(
            f"SELECT organization_id FROM {platform_key_table} WHERE key=%s", (token,)
        )
        if organization_uid is None:
            return None, None

        organization_identifier: str | None = cls.execute_query(
            f"SELECT organization_id FROM {organization_table} WHERE id=%s",
            (organization_uid,),
        )
        return organization_uid, organization_identifier

    @classmethod
    def execute_query(cls, query: str, params: tuple = ()) -> Any:
        """Execute a SQL query and return the first result."""
        cursor = be_db.execute_sql(query, params)
        result_row = cursor.fetchone()
        cursor.close()
        if not result_row or len(result_row) == 0:
            return None
        return result_row[0]
