from typing import Any

# Fields injected server-side (outside the request body) by mixins such as
# DefaultOrganizationMixin / AuditSerializer; clients never supply them.
SERVER_SET_UNIQUENESS_FIELDS = frozenset({"organization", "created_by", "modified_by"})


class DropServerSetUniquenessMixin:
    """Restore DRF 3.14 behaviour for server-set uniqueness fields.

    DRF 3.15 derives ``required=True`` and ``UniqueTogetherValidator``s from a
    model's multi-field ``UniqueConstraint``s (3.14 only looked at
    ``unique_together``). For org-scoped constraints that include server-set
    fields, that wrongly forces clients to POST ``organization`` and 400s every
    create/update. Strip those fields from both halves of the uniqueness
    machinery. The DB ``UniqueConstraint``s still enforce real duplicates, and
    ``IntegrityErrorMixin`` still surfaces them as clean validation errors.
    """

    def get_uniqueness_extra_kwargs(
        self,
        field_names: Any,
        declared_fields: Any,
        extra_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extra_kwargs, hidden_fields = super().get_uniqueness_extra_kwargs(
            field_names, declared_fields, extra_kwargs
        )
        for field in SERVER_SET_UNIQUENESS_FIELDS:
            extra_kwargs.pop(field, None)
            hidden_fields.pop(field, None)
        return extra_kwargs, hidden_fields

    def get_unique_together_validators(self) -> list[Any]:
        return [
            validator
            for validator in super().get_unique_together_validators()
            if not (set(getattr(validator, "fields", ())) & SERVER_SET_UNIQUENESS_FIELDS)
        ]
