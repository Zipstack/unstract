import abc


class DNSProviderInterface(abc.ABC):
    """DNSProviderInterface is an abstract base class that defines the
    interface for a DNS provider.

    Attributes:
        _app_fqdn (str): The fully qualified domain name (FQDN)
                         of the application.
        _subdomain (str): The subdomain for the DNS record.
        _domain (str): The domain for the DNS record.
        _top_level_domain (str): The top-level domain for the DNS record.
        _fqdn (str): The fully qualified domain name (FQDN) of the DNS record.

    Methods:
        __init__(
            self, subdomain: str, app_fqdn: str, configurations: dict[str, str]
        )
            Initializes the DNSProviderInterface object with
            the given subdomain, app_fqdn, and configurations.

        initialize(self, configurations: Dict[str, str]) -> None
            Initializes required instance variables from configuration.

        get_domain_components(self) -> Dict[str, str]
            Get the domain components for the DNS record.

        create_record(self) -> None
            Create a DNS record for the given subdomain.

        delete_record(self) -> None
            Delete a DNS record for the given subdomain.
    """

    def __init__(
        self, subdomain: str, app_fqdn: str, configurations: dict[str, str]
    ):
        self._app_fqdn = app_fqdn
        self._subdomain = subdomain
        self._domain = configurations["domain"]
        self._top_level_domain = configurations["top_level_domain"]
        self._fqdn = ".".join(
            [self._subdomain, self._domain, self._top_level_domain]
        )
        self.initialize(configurations)

    @abc.abstractmethod
    def initialize(self, configurations: dict[str, str]) -> None:
        """Initializes required instance variables from configuration.

        Args:
            configurations (Dict[str, str]): Configurations required by provider

        Returns:
            None
        """
        raise NotImplementedError

    def get_domain_components(self) -> dict[str, str]:
        """Get the domain components for the DNS record.

        This method returns a dictionary containing the components of
        the domain for the DNS record.
        The keys of the dictionary represent the different
        components of the domain, such as 'subdomain', 'domain', and
        'top-level domain'. The values of the dictionary represent
        the corresponding values for each component.

        Returns:
            dict: A dictionary containing the components of
                  the domain for the DNS record.

        Example:
            >>> dns_provider.get_domain_components()
            {
                'subdomain': 'www',
                'domain': 'example',
                'top_level_domain': 'com',
                'fqdn': 'www.example.com'
            }
        """
        return {
            "subdomain": self._subdomain,
            "domain": self._domain,
            "top_level_domain": self._top_level_domain,
            "fqdn": self._fqdn,
        }

    @abc.abstractmethod
    def create_record(self) -> None:
        """Create a DNS record for the given subdomain.

        Returns:
            None
        """
        raise NotImplementedError

    @abc.abstractmethod
    def delete_record(self) -> None:
        """Delete a DNS record for the given subdomain.

        Returns:
            None
        """
        raise NotImplementedError
