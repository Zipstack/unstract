import json
import os
from datetime import datetime, timedelta
from logging import Logger
from typing import Any, Optional

import peewee
import requests
from unstract.platform_service.constants import DBTableV2, FeatureFlag
from unstract.platform_service.exceptions import CustomException
from unstract.platform_service.utils import EnvManager

from unstract.flags.feature_flag import check_feature_flag_status

DB_SCHEMA = EnvManager.get_required_setting("DB_SCHEMA", "unstract_v2")


class AdapterInstanceRequestHelper:
    @staticmethod
    def get_adapter_instance_from_db(
        db_instance: peewee.PostgresqlDatabase,
        organization_id: str,
        adapter_instance_id: str,
        organization_uid: Optional[int] = None,
    ) -> dict[str, Any]:
        """Get adapter instance from Backend Database.

        Args:
            db_instance (peewee.PostgresqlDatabase): Backend DB
            organization_id (str): organization schema id
            adapter_instance_id (str): adapter instance id

        Returns:
            _type_: _description_
        """
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            query = (
                "SELECT id, adapter_id, adapter_metadata_b FROM "
                f'"{DB_SCHEMA}".{DBTableV2.ADAPTER_INSTANCE} x '
                f"WHERE id='{adapter_instance_id}' and "
                f"organization_id='{organization_uid}'"
            )
        else:
            query = (
                f"SELECT id, adapter_id, adapter_metadata_b FROM "
                f'"{organization_id}".adapter_adapterinstance x '
                f"WHERE id='{adapter_instance_id}'"
            )
        cursor = db_instance.execute_sql(query)
        result_row = cursor.fetchone()
        if not result_row:
            raise CustomException(message="Adapter not found", code=404)
        columns = [desc[0] for desc in cursor.description]
        data_dict: dict[str, Any] = dict(zip(columns, result_row))
        cursor.close()
        db_instance.close()
        return data_dict


class PromptStudioRequestHelper:
    @staticmethod
    def get_prompt_instance_from_db(
        db_instance: peewee.PostgresqlDatabase,
        organization_id: str,
        prompt_registry_id: str,
    ) -> dict[str, Any]:
        """Get prompt studio registry from Backend Database.

        Args:
            db_instance (peewee.PostgresqlDatabase): Backend DB
            organization_id (str): organization schema id
            prompt_registry_id (str): prompt_registry_id

        Returns:
            _type_: _description_
        """
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            query = (
                "SELECT prompt_registry_id, tool_spec, "
                "tool_metadata, tool_property FROM "
                f'"{DB_SCHEMA}".{DBTableV2.PROMPT_STUDIO_REGISTRY} x '
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
            raise CustomException(message="Custom Tool not found", code=404)
        columns = [desc[0] for desc in cursor.description]
        data_dict: dict[str, Any] = dict(zip(columns, result_row))
        cursor.close()
        db_instance.close()
        return data_dict


class CostCalculationHelper:
    def __init__(
        self,
        url: str,
        ttl_days: int,
        file_path: str,
        logger: Logger,
    ):
        self.ttl_days = ttl_days
        self.url = url
        self.file_path = file_path
        self.logger = logger

    def calculate_cost(self, model_name, provider, input_tokens, output_tokens):
        cost = 0.0
        item = None
        model_prices = self._get_model_prices()
        # Filter the model objects by model name
        filtered_models = {
            k: v for k, v in model_prices.items() if k.endswith(model_name)
        }
        # Check if the lite llm provider starts with the given provider
        for _, model_info in filtered_models.items():
            if provider in model_info.get("litellm_provider", ""):
                item = model_info
                break
        if item:
            input_cost_per_token = item.get("input_cost_per_token", 0)
            output_cost_per_token = item.get("output_cost_per_token", 0)
            cost += input_cost_per_token * input_tokens
            cost += output_cost_per_token * output_tokens
        return _format_float_positional(cost)

    def _get_model_prices(self):
        try:
            if os.path.exists(self.file_path):
                file_mtime = os.path.getmtime(self.file_path)
                file_expiry_date = datetime.fromtimestamp(file_mtime) + timedelta(
                    days=self.ttl_days
                )
                if datetime.now() < file_expiry_date:
                    # File exists and TTL has not expired, read and return content
                    with open(self.file_path, encoding="utf-8") as f:
                        return json.load(f)
                else:
                    # TTL expired, fetch updated JSON data from API
                    return self._fetch_and_save_json()
            else:
                # File does not exist, fetch JSON data from API
                return self._fetch_and_save_json()
        except Exception as e:
            self.logger.error("Error in calculate_cost: %s", e)
            return None

    def _fetch_and_save_json(self):
        try:
            # Fetch updated JSON data from API
            response = requests.get(self.url, timeout=10)
            if response.status_code == 200:
                json_data = response.json()
                # Save JSON data to file
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=4)
                # Set the file's modification time to indicate TTL
                expiry_date = datetime.now() + timedelta(days=self.ttl_days)
                expiry_timestamp = expiry_date.timestamp()
                os.utime(self.file_path, (expiry_timestamp, expiry_timestamp))
                self.logger.info(
                    "File '%s' updated successfully with TTL set to %d days.",
                    self.file_path,
                    self.ttl_days,
                )
                return json_data
            else:
                self.logger.error(
                    "Failed to fetch data from API. Status code: %d",
                    response.status_code,
                )
                return None
        except Exception as e:
            self.logger.error("Error fetching data from API: %s", e)
            return None


def _format_float_positional(value: float, precision: int = 10) -> str:
    formatted: str = f"{value:.{precision}f}"
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
