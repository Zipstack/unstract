import json
import os
from datetime import datetime, timedelta
from typing import Any, Optional

import requests
from flask import current_app as app
from unstract.platform_service.constants import FeatureFlag
from unstract.platform_service.env import Env
from unstract.platform_service.utils import format_float_positional

from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
    from datetime import timezone

    from unstract.sdk.exceptions import FileStorageError
    from unstract.sdk.file_storage import FileStorageProvider, PermanentFileStorage


class CostCalculationHelper:
    def __init__(
        self,
        url: str = Env.MODEL_PRICES_URL,
        ttl_days: int = Env.MODEL_PRICES_TTL_IN_DAYS,
        file_path: str = Env.MODEL_PRICES_FILE_PATH,
    ):
        self.ttl_days = ttl_days
        self.url = url
        self.file_path = file_path

        if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
            self.file_storage, self.file_path = self.__get_storage_credentials()
        self.model_token_data = self._get_model_token_data()

    if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):

        def __get_storage_credentials(self) -> tuple[PermanentFileStorage, str]:
            try:
                # Not creating constants for now for the keywords below as this
                # logic ought to change in the near future to maintain unformity
                # across services
                file_storage = json.loads(os.environ.get("FILE_STORAGE_CREDENTIALS"))
                provider = FileStorageProvider(file_storage["provider"])
                credentials = file_storage["credentials"]
                file_path = file_storage["file_path"]
                return PermanentFileStorage(provider, **credentials), file_path
            except FileStorageError as e:
                app.logger.error(
                    "Error while initialising storage: %s",
                    e,
                    stack_info=True,
                    exc_info=True,
                )

    def calculate_cost(
        self, model_name: str, provider: str, input_tokens: int, output_tokens: int
    ) -> str:
        cost = 0.0
        item = None

        if not self.model_token_data:
            if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
                return json.loads(format_float_positional(cost))
            else:
                return format_float_positional(cost)
        # Filter the model objects by model name
        filtered_models = {
            k: v for k, v in self.model_token_data.items() if k.endswith(model_name)
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
        return format_float_positional(cost)

    def _get_model_token_data(self) -> Optional[dict[str, Any]]:
        try:
            if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
                # File does not exist, fetch JSON data from API
                if not self.file_storage.exists(self.file_path):
                    return self._fetch_and_save_json()

                file_mtime = self.file_storage.modification_time(self.file_path)
                file_expiry_date = file_mtime + timedelta(days=self.ttl_days)
                file_expiry_date_utc = file_expiry_date.replace(tzinfo=timezone.utc)
                now_utc = datetime.now().replace(tzinfo=timezone.utc)

                if now_utc < file_expiry_date_utc:
                    app.logger.info(f"Reading model token data from {self.file_path}")
                    # File exists and TTL has not expired, read and return content
                    file_contents = self.file_storage.read(
                        self.file_path, mode="r", encoding="utf-8"
                    )
                    return json.loads(file_contents)
                else:
                    # TTL expired, fetch updated JSON data from API
                    return self._fetch_and_save_json()
            else:
                # File does not exist, fetch JSON data from API
                if not os.path.exists(self.file_path):
                    return self._fetch_and_save_json()

                file_mtime = os.path.getmtime(self.file_path)
                file_expiry_date = datetime.fromtimestamp(file_mtime) + timedelta(
                    days=self.ttl_days
                )
                if datetime.now() < file_expiry_date:
                    app.logger.info(f"Reading model token data from {self.file_path}")
                    # File exists and TTL has not expired, read and return content
                    with open(self.file_path, encoding="utf-8") as f:
                        return json.load(f)
                else:
                    # TTL expired, fetch updated JSON data from API
                    return self._fetch_and_save_json()
        except Exception as e:
            app.logger.warning(
                "Error in calculate_cost: %s", e, stack_info=True, exc_info=True
            )
            return None

    def _fetch_and_save_json(self) -> Optional[dict[str, Any]]:
        """Fetch model's price and token data from the URL.

        Caches it in a file with the mentioned TTL

        Returns:
            Optional[dict[str, Any]]: JSON of model and price / token data
        """
        try:
            # Fetch updated JSON data from API
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            json_data = response.json()
            # Save JSON data to file
            if check_feature_flag_status(FeatureFlag.REMOTE_FILE_STORAGE):
                self.file_storage.json_dump(
                    path=self.file_path,
                    mode="w",
                    encoding="utf-8",
                    data=json_data,
                    ensure_ascii=False,
                    indent=4,
                )
            else:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=4)
                # Set the file's modification time to indicate TTL
                expiry_date = datetime.now() + timedelta(days=self.ttl_days)
                expiry_timestamp = expiry_date.timestamp()
                os.utime(self.file_path, (expiry_timestamp, expiry_timestamp))

            app.logger.info(
                "File '%s' updated successfully with TTL set to %d days.",
                self.file_path,
                self.ttl_days,
            )
            return json_data
        except Exception as e:
            app.logger.error(
                "Error fetching data from API: %s", e, stack_info=True, exc_info=True
            )
            return None
