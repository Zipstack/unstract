from typing import Any

from playhouse.pool import PooledPostgresqlDatabase
from unstract.platform_service.constants import DBTableV2, FeatureFlag
from unstract.platform_service.exceptions import APIError

from unstract.flags.feature_flag import check_feature_flag_status


class PromptStudioRequestHelper:
    @staticmethod
    def get_prompt_instance_from_db(
        db_instance: PooledPostgresqlDatabase,
        organization_id: str,
        prompt_registry_id: str,
    ) -> dict[str, Any]:
        """Get prompt studio registry from Backend Database.

        Args:
            db_instance (PooledPostgresqlDatabase): Backend DB Connection Pool
            organization_id (str): organization schema id
            prompt_registry_id (str): prompt_registry_id

        Returns:
            _type_: _description_
        """
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            query = (
                "SELECT prompt_registry_id, tool_spec, "
                "tool_metadata, tool_property FROM "
                f"{DBTableV2.PROMPT_STUDIO_REGISTRY} x "
                f"WHERE prompt_registry_id='{prompt_registry_id}'"
            )
        else:
            query = (
                f"SELECT prompt_registry_id, tool_spec, "
                f"tool_metadata, tool_property FROM "
                f'"{organization_id}".prompt_studio_registry_promptstudioregistry x'
                f" WHERE prompt_registry_id='{prompt_registry_id}'"
            )
        cursor = db_instance.execute_sql(query)
        result_row = cursor.fetchone()
        if not result_row:
            raise APIError(message="Custom Tool not found", code=404)
        columns = [desc[0] for desc in cursor.description]
        data_dict: dict[str, Any] = dict(zip(columns, result_row))
        cursor.close()
        db_instance.close()
        return data_dict
