"""API DTO extensions for cloud deployments.

This plugin extends OSS DTOs with cloud-specific features like
highlight data in Postman collections.
"""

from .postman_collection import HighlightPostmanDto


class ApiDtoService:
    """Service for providing cloud-specific API DTOs."""

    def get_postman_dto(self):
        """Get the Postman collection DTO class for cloud features.

        Returns:
            Class: HighlightPostmanDto class for creating Postman collections
                   with cloud-specific features like highlight data API.
        """
        return HighlightPostmanDto


metadata = {
    "version": "1.0.0",
    "name": "api_dto",
    "is_active": True,
    "description": "API DTO extensions for cloud-specific features",
    "service_class": ApiDtoService,
}

__all__ = ["metadata", "ApiDtoService"]
