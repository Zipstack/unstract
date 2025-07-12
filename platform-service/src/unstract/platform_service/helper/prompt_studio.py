from typing import Any

from unstract.core.flask.exceptions import APIError
from unstract.platform_service.constants import DBTable
from unstract.platform_service.extensions import db
from unstract.platform_service.utils import EnvManager

DB_SCHEMA = EnvManager.get_required_setting("DB_SCHEMA", "unstract")


class PromptStudioRequestHelper:
    @staticmethod
    def get_prompt_instance_from_db(
        organization_id: str,
        prompt_registry_id: str,
    ) -> dict[str, Any]:
        """Get prompt studio registry from Backend Database.

        Args:
            organization_id (str): organization schema id
            prompt_registry_id (str): prompt_registry_id

        Returns:
            _type_: _description_
        """
        query = (
            "SELECT prompt_registry_id, tool_spec, "
            "tool_metadata, tool_property FROM "
            f'"{DB_SCHEMA}".{DBTable.PROMPT_STUDIO_REGISTRY} x '
            f"WHERE prompt_registry_id='{prompt_registry_id}'"
        )
        cursor = db.execute_sql(query)
        result_row = cursor.fetchone()
        if not result_row:
            raise APIError(
                message=f"Prompt studio project with UUID '{prompt_registry_id}' is not found.",
                code=404,
            )
        columns = [desc[0] for desc in cursor.description]
        data_dict: dict[str, Any] = dict(zip(columns, result_row, strict=False))
        cursor.close()
        return data_dict

    @staticmethod
    def get_llm_profile_instance_from_db(
        organization_id: str,
        llm_profile_id: str,
    ) -> dict[str, Any]:
        """Get llm profile instance from Backend Database.

        Args:
            organization_id (str): organization schema id
            llm_profile_id (str): llm_profile_id

        Returns:
            _type_: _description_
        """
        query = (
            "SELECT * FROM "
            f'"{DB_SCHEMA}".{DBTable.LLM_PROFILE_MANAGER} x '
            f"WHERE profile_id='{llm_profile_id}'"
        )
        cursor = db.execute_sql(query)
        result_row = cursor.fetchone()
        if not result_row:
            raise APIError(
                message=f"LLM profile with UUID '{llm_profile_id}' is not found.",
                code=404,
            )
        columns = [desc[0] for desc in cursor.description]
        data_dict: dict[str, Any] = dict(zip(columns, result_row, strict=False))
        cursor.close()
        return data_dict
