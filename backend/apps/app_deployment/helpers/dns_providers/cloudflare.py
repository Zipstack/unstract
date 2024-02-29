"""Module for cloudflare dns provider."""
from functools import lru_cache
from typing import Optional

from apps.app_deployment.helpers.dns_providers.interface import (
    DNSProviderInterface,
)
from CloudFlare import CloudFlare


@lru_cache(maxsize=128)
def get_zone_id(client: CloudFlare, zone_name: str) -> Optional[str]:
    """Retrieves the zone ID for a given zone name using the CloudFlare API.

    Args:
        client: An object of type `CloudFlare`
                representing the CloudFlare client.
        zone_name: A string representing the name of the zone for which
                   the zone ID needs to be retrieved.

    Returns:
        A string representing the zone ID for the given `zone_name`
    """
    zones = client.zones.get(params={"name": zone_name, "per_page": 1})
    zone_id = zones[0]["id"]
    return str(zone_id)


class CloudFlareDNSProvider(DNSProviderInterface):
    """A class representing a DNS provider for CloudFlare.

    This class extends the abstract base class `DNSProviderInterface`
    and provides implementation for creating and deleting DNS records using
    the CloudFlare API.

    Attributes:
        _client (CloudFlare): An object representing the CloudFlare client.
        _zone_name (str): The name of the zone associated with the DNS records.
        _zone_id (str): The ID of the zone associated with the DNS records.
        _dns_record (dict): A dictionary representing the
                            DNS record to be created.

    Methods:
        initialize(configurations: dict[str, str]) -> None:
            Initializes the required instance variables
            from the given configurations.

        create_record() -> None:
            Creates a DNS record for the given subdomain
            using the CloudFlare API.

        delete_record() -> None:
            Deletes a DNS record for the given subdomain
            using the CloudFlare API.
    """

    def initialize(self, configurations: dict[str, str]) -> None:
        self._client = CloudFlare(token=configurations["token"])
        self._zone_name = f"{self._domain}.{self._top_level_domain}"
        self._zone_id = get_zone_id(self._client, self._zone_name)
        self._dns_record = {
            "name": self._fqdn,
            "type": "CNAME",
            "content": self._app_fqdn,
            "comment": "Created from unstract backend",
        }

    def create_record(self) -> None:
        """Create a DNS record for the given subdomain.

        Returns:
            None
        """
        # TODO: Add logs
        self._client.zones.dns_records.post(
            self._zone_id, data=self._dns_record
        )

    def delete_record(self) -> None:
        """Delete a DNS record for the given subdomain.

        Returns:
            None
        """
        # TODO: Add the delete implementation.
        raise NotImplementedError
