import importlib
import os
from logging import Logger
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, current_app
from unstract.prompt_service.authentication_middleware import AuthenticationMiddleware
from unstract.prompt_service.constants import FeatureFlag
from unstract.prompt_service.db_utils import DBUtils
from unstract.prompt_service.env_manager import EnvLoader

from unstract.flags.feature_flag import check_feature_flag_status

DB_SCHEMA = EnvLoader.get_env_or_die("DB_SCHEMA", "unstract_v2")

load_dotenv()


class PluginException(Exception):
    """All exceptions raised from a plugin."""


def plugin_loader(app: Flask) -> dict[str, dict[str, Any]]:
    """Loads plugins found in the plugins root dir.

    Each plugin:
    * needs to be a package dir AND
    * should contain a src/__init__.py which exports below:

        metadata: dict[str, Any] = {
            "version": str,
            "name": str,
            "entrypoint_cls": class,
            "exception_cls": class,
            "disable": bool
        }
    """
    plugins_dir: Path = Path(os.path.dirname(__file__)) / "plugins"
    plugins_pkg = "unstract.prompt_service.plugins"

    if not plugins_dir.exists():
        app.logger.info(f"Plugins dir not found: {plugins_dir}. Skipping.")
        return {}

    plugins: dict[str, dict[str, Any]] = {}
    app.logger.info(f"Loading plugins from: {plugins_dir}")

    for pkg in os.listdir(os.fspath(plugins_dir)):
        if pkg.endswith(".so"):
            pkg = pkg.split(".")[0]
        pkg_anchor = f"{plugins_pkg}.{pkg}.src"
        try:
            module = importlib.import_module(pkg_anchor)
        except ImportError as e:
            app.logger.error(f"Failed to load plugin ({pkg}): {str(e)}")
            continue

        if not hasattr(module, "metadata"):
            app.logger.warn(f"Plugin metadata not found: {pkg}")
            continue

        metadata: dict[str, Any] = module.metadata
        if metadata.get("disable", False):
            app.logger.info(f"Ignore disabled plugin: {pkg} v{metadata['version']}")
            continue

        try:
            plugins[metadata["name"]] = {
                "version": metadata["version"],
                "entrypoint_cls": metadata["entrypoint_cls"],
                "exception_cls": metadata["exception_cls"],
            }
            app.logger.info(f"Loaded plugin: {pkg} v{metadata['version']}")
        except KeyError as e:
            app.logger.error(f"Invalid metadata for plugin '{pkg}': {str(e)}")

    if not plugins:
        app.logger.info("No plugins found.")

    return plugins


def query_usage_metadata(db, token: str, metadata: dict[str, Any]) -> dict[str, Any]:
    if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
        return query_usage_metadata_v2(db, token, metadata)
    org_id: str = AuthenticationMiddleware.get_account_from_bearer_token(token)
    run_id: str = metadata["run_id"]
    query: str = f"""
        SELECT
            usage_type,
            llm_usage_reason,
            model_name,
            SUM(prompt_tokens) AS input_tokens,
            SUM(completion_tokens) AS output_tokens,
            SUM(total_tokens) AS total_tokens,
            SUM(embedding_tokens) AS embedding_tokens,
            SUM(cost_in_dollars) AS cost_in_dollars
        FROM "{org_id}"."token_usage"
        WHERE run_id = %s
        GROUP BY usage_type, llm_usage_reason, model_name;
    """
    logger: Logger = current_app.logger
    try:
        with db.atomic():
            logger.info(
                "Querying usage metadata for org_id: %s, run_id: %s", org_id, run_id
            )
            cursor = db.execute_sql(query, (run_id,))
            results: list[tuple] = cursor.fetchall()
            # Process results as needed
            for row in results:
                key, item = _get_key_and_item(row)
                # Initialize the key as an empty list if it doesn't exist
                if key not in metadata:
                    metadata[key] = []
                # Append the item to the list associated with the key
                metadata[key].append(item)
    except Exception as e:
        logger.error(f"Error executing querying usage metadata: {e}")
    return metadata


def query_usage_metadata_v2(db, token: str, metadata: dict[str, Any]) -> dict[str, Any]:
    DB_SCHEMA = EnvLoader.get_env_or_die("DB_SCHEMA", "unstract_v2")
    organization_uid, org_id = DBUtils.get_organization_from_bearer_token(token)
    run_id: str = metadata["run_id"]
    query: str = f"""
        SELECT
            usage_type,
            llm_usage_reason,
            model_name,
            SUM(prompt_tokens) AS input_tokens,
            SUM(completion_tokens) AS output_tokens,
            SUM(total_tokens) AS total_tokens,
            SUM(embedding_tokens) AS embedding_tokens,
            SUM(cost_in_dollars) AS cost_in_dollars
        FROM "{DB_SCHEMA}"."token_usage_v2"
        WHERE run_id = %s and organization_id = %s
        GROUP BY usage_type, llm_usage_reason, model_name;
    """
    logger: Logger = current_app.logger
    try:
        with db.atomic():
            logger.info(
                "Querying usage metadata for org_id: %s, run_id: %s", org_id, run_id
            )
            cursor = db.execute_sql(query, (run_id, organization_uid))
            results: list[tuple] = cursor.fetchall()
            # Process results as needed
            for row in results:
                key, item = _get_key_and_item(row)
                # Initialize the key as an empty list if it doesn't exist
                if key not in metadata:
                    metadata[key] = []
                # Append the item to the list associated with the key
                metadata[key].append(item)
    except Exception as e:
        logger.error(f"Error executing querying usage metadata: {e}")
    return metadata


def _get_key_and_item(row: tuple) -> tuple[str, dict[str, Any]]:
    (
        usage_type,
        llm_usage_reason,
        model_name,
        input_tokens,
        output_tokens,
        total_tokens,
        embedding_tokens,
        cost_in_dollars,
    ) = row
    cost_in_dollars: str = _format_float_positional(cost_in_dollars)
    key: str = usage_type
    item: dict[str, Any] = {
        "model_name": model_name,
        "cost_in_dollars": cost_in_dollars,
    }
    if llm_usage_reason:
        key = f"{llm_usage_reason}_{key}"
        item["input_tokens"] = input_tokens
        item["output_tokens"] = output_tokens
        item["total_tokens"] = total_tokens
    else:
        item["embedding_tokens"] = embedding_tokens
    return key, item


def _format_float_positional(value: float, precision: int = 10) -> str:
    formatted: str = f"{value:.{precision}f}"
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
