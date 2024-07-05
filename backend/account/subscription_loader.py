import logging
import os
from importlib import import_module
from typing import Any

from django.apps import apps
from django.utils import timezone

logger = logging.getLogger(__name__)


class SubscriptionConfig:
    """Loader config for subscription plugins."""

    PLUGINS_APP = "plugins"
    PLUGIN_DIR = "subscription"
    MODULE = "module"
    METADATA = "metadata"
    METADATA_NAME = "name"
    METADATA_SERVICE_CLASS = "service_class"
    METADATA_IS_ACTIVE = "is_active"


def load_plugins() -> list[Any]:
    """Iterate through the subscription plugins and register them."""
    plugins_app = apps.get_app_config(SubscriptionConfig.PLUGINS_APP)
    package_path = plugins_app.module.__package__
    subscription_dir = os.path.join(plugins_app.path, SubscriptionConfig.PLUGIN_DIR)
    subscription_package_path = f"{package_path}.{SubscriptionConfig.PLUGIN_DIR}"
    subscription_plugins: list[Any] = []

    if not os.path.exists(subscription_dir):
        return subscription_plugins

    for item in os.listdir(subscription_dir):
        # Loads a plugin if it is in a directory.
        if os.path.isdir(os.path.join(subscription_dir, item)):
            subscription_module_name = item
        # Loads a plugin if it is a shared library.
        # Module name is extracted from shared library name.
        # `subscription.platform_architecture.so` will be file name and
        # `subscription` will be the module name.
        elif item.endswith(".so"):
            subscription_module_name = item.split(".")[0]
        else:
            continue
        try:
            full_module_path = f"{subscription_package_path}.{subscription_module_name}"
            module = import_module(full_module_path)
            metadata = getattr(module, SubscriptionConfig.METADATA, {})

            if metadata.get(SubscriptionConfig.METADATA_IS_ACTIVE, False):
                subscription_plugins.append(
                    {
                        SubscriptionConfig.MODULE: module,
                        SubscriptionConfig.METADATA: module.metadata,
                    }
                )
                logger.info(
                    "Loaded subscription plugin: %s, is_active: %s",
                    module.metadata[SubscriptionConfig.METADATA_NAME],
                    module.metadata[SubscriptionConfig.METADATA_IS_ACTIVE],
                )
            else:
                logger.info(
                    "subscription plugin %s is not active.",
                    subscription_module_name,
                )
        except ModuleNotFoundError as exception:
            logger.error(
                "Error while importing subscription plugin: %s",
                exception,
            )

    if len(subscription_plugins) == 0:
        logger.info("No subscription plugins found.")

    return subscription_plugins


def validate_etl_run(org_id: str) -> bool:
    """Method to check subscription status before ETL runs.

    Args:
        org_id: The ID of the organization.

    Returns:
        A boolean indicating whether the pre-run check passed or not.
    """
    try:
        from pluggable_apps.subscription.subscription_helper import SubscriptionHelper
    except ModuleNotFoundError:
        logger.error("Subscription plugin not found.")
        return False

    org_plans = SubscriptionHelper.get_subscription(org_id)
    if not org_plans or not org_plans.is_active:
        return False

    if org_plans.is_paid:
        return True

    if timezone.now() >= org_plans.end_date:
        logger.debug(f"Trial expired for org {org_id}")
        return False

    return True
