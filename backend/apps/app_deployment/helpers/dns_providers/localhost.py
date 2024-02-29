"""Module for handling localhost."""

from apps.app_deployment.helpers.dns_providers.interface import (
    DNSProviderInterface,
)


class LocalhostDNSProvider(DNSProviderInterface):
    """LocalhostDNSProvider is a class that represents a DNS provider for
    localhost."""

    def initialize(self, configurations: dict[str, str]) -> None:
        """In case of localhost do nothing.

        Returns:
            None
        """

    def create_record(self) -> None:
        """In case of localhost do nothing.

        Returns:
            None
        """

    def delete_record(self) -> None:
        """In case of localhost do nothing.

        Returns:
            None
        """
