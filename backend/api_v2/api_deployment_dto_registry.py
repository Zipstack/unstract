import logging
from typing import Any, Optional

from api_v2.postman_collection.dto import PostmanCollection
from plugins.api.dto import metadata

logger = logging.getLogger(__name__)


class ApiDeploymentDTORegistry:
    _dto_class: Optional[Any] = None  # Store the selected DTO class (cached)

    @classmethod
    def load_dto(cls) -> Optional[Any]:
        class_name = PostmanCollection.__name__
        if metadata.get(class_name):
            return metadata[class_name].class_name
        return PostmanCollection  # Return as soon as we find a valid DTO

    @classmethod
    def get_dto(cls) -> Optional[type]:
        """Returns the first available DTO class, or None if unavailable."""
        return cls.load_dto()
