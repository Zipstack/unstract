import logging
from typing import Any

from plugins import get_plugin

from api_v2.postman_collection.dto import PostmanCollection

logger = logging.getLogger(__name__)


class ApiDeploymentDTORegistry:
    _dto_class: Any | None = None  # Store the selected DTO class (cached)

    @classmethod
    def load_dto(cls) -> Any | None:
        """Load DTO from plugin or return default PostmanCollection.

        Checks if the api_dto plugin is available and gets the Postman DTO
        via the service, otherwise returns the base PostmanCollection class.
        """
        plugin = get_plugin("api_dto")
        if plugin:
            service = plugin["service_class"]()
            return service.get_postman_dto()
        return PostmanCollection

    @classmethod
    def get_dto(cls) -> type | None:
        """Returns the first available DTO class, or None if unavailable."""
        return cls.load_dto()
