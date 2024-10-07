from typing import Any, Optional

from unstract.platform_service.constants import DBTableV2, FeatureFlag
from unstract.platform_service.exceptions import APIError
from unstract.platform_service.extensions import db
from unstract.platform_service.utils import EnvManager

from unstract.flags.feature_flag import check_feature_flag_status

DB_SCHEMA = EnvManager.get_required_setting("DB_SCHEMA", "unstract_v2")


class AdapterInstanceRequestHelper:
    @staticmethod
    def get_adapter_instance_from_db(
        organization_id: str,
        adapter_instance_id: str,
        organization_uid: Optional[int] = None,
    ) -> dict[str, Any]:
        """Get adapter instance from Backend Database.

        Args:
            organization_id (str): organization schema id
            adapter_instance_id (str): adapter instance id

        Returns:
            _type_: _description_
        """
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            query = (
                "SELECT id, adapter_id, adapter_name, adapter_type, adapter_metadata_b"
                f' FROM "{DB_SCHEMA}".{DBTableV2.ADAPTER_INSTANCE} x '
                f"WHERE id='{adapter_instance_id}' and "
                f"organization_id='{organization_uid}'"
            )
        else:
            query = (
                f"SELECT id, adapter_id, adapter_name, adapter_type, adapter_metadata_b"
                f' FROM "{organization_id}".adapter_adapterinstance x '
                f"WHERE id='{adapter_instance_id}'"
            )
        cursor = db.execute_sql(query)
        result_row = cursor.fetchone()
        if not result_row:
            raise APIError(
                message=f"Adapter '{adapter_instance_id}' not found", code=404
            )
        columns = [desc[0] for desc in cursor.description]
        data_dict: dict[str, Any] = dict(zip(columns, result_row))
        cursor.close()
        return data_dict
