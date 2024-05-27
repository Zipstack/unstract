"""Module to load appropriate dns provider as per configuration."""

import json

from apps.app_deployment.helpers.dns_providers.cloudflare import CloudFlareDNSProvider
from apps.app_deployment.helpers.dns_providers.interface import DNSProviderInterface
from apps.app_deployment.helpers.dns_providers.localhost import LocalhostDNSProvider
from apps.app_deployment.models import DNSProvider
from django.conf import settings


class InvalidDNSProviderException(Exception):
    """Exception raised when an invalid DNS provider is configured."""


def get_dns_provider(
    subdomain: str,
    app_fqdn: str,
) -> DNSProviderInterface:
    """Retrieves the appropriate DNS provider based on the given subdomain and
    app_fqdn.

    Args:
        subdomain (str): The subdomain for which the DNS provider is needed.
        app_fqdn (str): The fully qualified domain name of the application.

    Returns:
        DNSProviderInterface: An instance of the DNS provider class that
                              implements the DNSProviderInterface.

    Raises:
        InvalidDNSProviderException: If the provider class is not available or
                                     if the configurations are missing.
    """
    #  Look up dictionary to select provider class
    provider_lookup = {
        DNSProvider.CLOUDFLARE: CloudFlareDNSProvider,
        DNSProvider.LOCALHOST: LocalhostDNSProvider,
    }
    dns_provider = settings.DNS_PROVIDER
    provider = provider_lookup.get(dns_provider)
    if not provider:
        # Raises error when the provider class is not available
        raise InvalidDNSProviderException(f"Invalid dns_provider name: {dns_provider}")
    configurations = json.loads(settings.DNS_PROVIDER_CONFIG)
    return provider(
        subdomain,
        app_fqdn,
        configurations,
    )
