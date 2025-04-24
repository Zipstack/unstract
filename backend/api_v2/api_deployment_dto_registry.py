import logging
from typing import Any

from plugins.api.dto import metadata

from api_v2.postman_collection.dto import PostmanCollection

logger = logging.getLogger(__name__)


class ApiDeploymentDTORegistry:
    _dto_class: Any | None = None  # Store the selected DTO class (cached)

    @classmethod
    def load_dto(cls) -> Any | None:
        class_name = PostmanCollection.__name__
        if metadata.get(class_name):
            return metadata[class_name].class_name
        return PostmanCollection  # Return as soon as we find a valid DTO

    @classmethod
    def get_dto(cls) -> type | None:
        """Returns the first available DTO class, or None if unavailable."""
        return cls.load_dto()
