from typing import Any

from unstract.core.flask.exceptions import APIError
from unstract.platform_service.constants import DBTable
from unstract.platform_service.extensions import safe_cursor
from unstract.platform_service.utils import EnvManager

DB_SCHEMA = EnvManager.get_required_setting("DB_SCHEMA", "unstract")


class AdapterInstanceRequestHelper:
    @staticmethod
    def get_adapter_instance_from_db(
        organization_id: str,
        adapter_instance_id: str,
        organization_uid: int | None = None,
    ) -> dict[str, Any]:
        """Get adapter instance from Backend Database.

        Args:
            organization_id (str): organization schema id
            adapter_instance_id (str): adapter instance id

        Returns:
            _type_: _description_
        """
        query = (
            "SELECT id, adapter_id, adapter_name, adapter_type, adapter_metadata_b,"
            " is_available"
            f' FROM "{DB_SCHEMA}".{DBTable.ADAPTER_INSTANCE} x '
            f"WHERE id=%s and organization_id=%s"
        )
        with safe_cursor(query, (adapter_instance_id, organization_uid)) as cursor:
            result_row = cursor.fetchone()
            if not result_row:
                raise APIError(
                    message=f"Adapter '{adapter_instance_id}' not found", code=404
                )
            columns = [desc[0] for desc in cursor.description]
            data_dict: dict[str, Any] = dict(zip(columns, result_row, strict=False))
            # Deprecated adapters are no longer in the SDK registry, so resolving
            # one would fail with an unrelated error further down the call.
            if not data_dict.pop("is_available", True):
                adapter_name = data_dict.get("adapter_name") or adapter_instance_id
                raise APIError(
                    message=(
                        f"Adapter '{adapter_name}' has been deprecated and can no "
                        "longer be used. Please reconfigure with a supported adapter."
                    ),
                    code=400,
                )
            return data_dict
