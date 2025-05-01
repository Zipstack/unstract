import importlib
import logging
import os
from typing import Dict, List, Optional, Type

from django.conf import settings

from account_v2.models import Subscription
from account_v2.subscription_base import SubscriptionBase

logger = logging.getLogger(__name__)


class SubscriptionLoader:
    """
    Loads subscription modules dynamically.
    """

    def __init__(self):
        self.subscriptions: Dict[str, Type[SubscriptionBase]] = {}
        self.load_subscriptions()

    def load_subscriptions(self) -> None:
        """
        Load all subscription modules from the subscriptions directory.
        """
        subscription_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "subscriptions"
        )
        subscription_files = [
            f[:-3]
            for f in os.listdir(subscription_dir)
            if f.endswith(".py") and f != "__init__.py"
        ]

        # Define a whitelist of allowed subscription modules
        allowed_modules = set(subscription_files)

        for subscription_file in subscription_files:
            try:
                module_path = f"account_v2.subscriptions.{subscription_file}"
                
                # Check if the module is in the whitelist
                if subscription_file not in allowed_modules:
                    logger.error(f"Attempted to load unauthorized module: {module_path}")
                    continue
                
                module = importlib.import_module(module_path)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, SubscriptionBase)
                        and attr != SubscriptionBase
                    ):
                        self.subscriptions[attr.subscription_type] = attr
                        logger.info(f"Loaded subscription: {attr.subscription_type}")
            except (ImportError, AttributeError) as e:
                logger.error(f"Error loading subscription {subscription_file}: {e}")

    def get_subscription_class(
        self, subscription_type: str
    ) -> Optional[Type[SubscriptionBase]]:
        """
        Get the subscription class for the given subscription type.

        Args:
            subscription_type: The type of subscription to get.

        Returns:
            The subscription class or None if not found.
        """
        return self.subscriptions.get(subscription_type)

    def get_subscription_classes(
        self, subscription_types: List[str]
    ) -> List[Type[SubscriptionBase]]:
        """
        Get the subscription classes for the given subscription types.

        Args:
            subscription_types: The types of subscriptions to get.

        Returns:
            A list of subscription classes.
        """
        return [
            self.subscriptions[subscription_type]
            for subscription_type in subscription_types
            if subscription_type in self.subscriptions
        ]

    def get_subscription_instance(
        self, subscription: Subscription
    ) -> Optional[SubscriptionBase]:
        """
        Get an instance of the subscription class for the given subscription.

        Args:
            subscription: The subscription to get an instance for.

        Returns:
            An instance of the subscription class or None if not found.
        """
        subscription_class = self.get_subscription_class(subscription.subscription_type)
        if subscription_class:
            return subscription_class(subscription)
        return None
