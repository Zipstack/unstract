import json
import os
from datetime import datetime, timedelta
from typing import Any, Optional

import requests
from flask import current_app as app
from singleton_decorator import singleton
from unstract.platform_service.env import Env
from unstract.platform_service.utils import format_float_positional


@singleton
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
        self.model_token_data = self._get_model_token_data()

    def calculate_cost(
        self, model_name: str, provider: str, input_tokens: int, output_tokens: int
    ) -> str:
        cost = 0.0
        item = None

        if not self.model_token_data:
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
            app.logger.error("Error in calculate_cost: %s", e)
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
            app.logger.error("Error fetching data from API: %s", e)
            return None
