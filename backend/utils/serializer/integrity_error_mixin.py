from django.db import IntegrityError
from rest_framework.exceptions import ValidationError


class IntegrityErrorMixin:
    """Mixin to handle IntegrityError across multiple serializers for unique
    constraint violations."""

    unique_error_message_map: dict[str, dict[str, str]] = {}

    def save(self, **kwargs):
        try:
            return super().save(**kwargs)
        except IntegrityError as e:
            self.handle_integrity_error(e)

    def handle_integrity_error(self, error):
        """General method to handle IntegrityError based on the
        unique_error_message_map.

        Each serializer or model can define its specific unique
        constraint violations and error messages.
        """
        for (
            unique_field,
            field_error_message_map,
        ) in self.unique_error_message_map.items():
            if unique_field in str(error):
                field = field_error_message_map.get("field")
                message = field_error_message_map.get("message")
                raise ValidationError({field: message})

        # Default message if the error doesn't match any known unique constraints
        raise ValidationError(
            {"detail": "An error occurred while saving. Please try again."}
        )
