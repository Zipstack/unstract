from typing import Optional

from django.db import models, transaction


class CloneUtil:
    @staticmethod
    def get_unique_fields(model: models.Model) -> list:
        unique_fields = set()
        for field in model._meta.fields:
            if (
                field.unique
                and not field.primary_key
                and not isinstance(field, models.ForeignKey)
            ):
                unique_fields.add(field.name)
        for constraint in model._meta.constraints:
            if isinstance(constraint, models.UniqueConstraint):
                for field_name in constraint.fields:
                    field = model._meta.get_field(field_name)
                    if not isinstance(field, models.ForeignKey):
                        unique_fields.add(field_name)
        return list(unique_fields)

    @staticmethod
    def clone_model_instance(
        instance: models.Model,
        parent: Optional[models.Model] = None,
        null_fields: Optional[list[str]] = None,
        new_user: Optional[models.Model] = None,
    ) -> models.Model:
        """Clones a model instance and its related objects recursively,
        assigning a new primary key.

        Takes into account unique constraints by allowing the user to
        provide overrides for unique fields via kwargs.
        """
        ModelClass = instance.__class__
        related_fields = [
            field
            for field in ModelClass._meta.get_fields()
            if field.one_to_many or field.one_to_one
        ]

        # Get the unique fields for the instance
        unique_fields = CloneUtil.get_unique_fields(ModelClass)  # type: ignore

        # Clone the instance without primary key and unique fields
        cloned_instance = ModelClass(
            **{
                field.name: getattr(instance, field.name)
                for field in ModelClass._meta.fields
                if not field.primary_key and field.name not in unique_fields
            }
        )

        # Customize unique fields
        for field_name in unique_fields:
            field = ModelClass._meta.get_field(field_name)
            default_value = field.get_default() if callable(field.get_default) else None
            setattr(
                cloned_instance,
                field_name,
                (
                    default_value
                    if default_value is not None
                    else f"{getattr(instance, field_name)}_copy"
                ),
            )
            # original_value = getattr(instance, field_name)
            # if original_value is not None:
            #     setattr(cloned_instance, field_name, f"{original_value}_copy")
            # else:
            #     setattr(cloned_instance, field_name, "copy")

        # Set the specified field to null
        if null_fields:
            for field_name in null_fields:
                setattr(cloned_instance, field_name, None)

        # Change the user value if specified
        if new_user:
            setattr(cloned_instance, "created_by", new_user)
            setattr(cloned_instance, "modified_by", new_user)

        # Save the cloned instance
        cloned_instance.save()

        # Update foreign key in parent if provided
        if parent:
            for field in ModelClass._meta.fields:
                if (
                    isinstance(field, models.ForeignKey)
                    and field.related_model == parent.__class__
                ):
                    setattr(cloned_instance, field.name, parent)
            cloned_instance.save()

        with transaction.atomic():
            for field in related_fields:
                if field.one_to_many:
                    related_objects = getattr(instance, field.get_accessor_name()).all()
                    for related_object in related_objects:
                        # Clone the related object, setting the new parent
                        CloneUtil.clone_model_instance(
                            related_object, parent=cloned_instance
                        )
                elif field.one_to_one:
                    try:
                        related_object = getattr(instance, field.name)
                        if related_object:
                            CloneUtil.clone_model_instance(
                                related_object, parent=cloned_instance
                            )
                    except field.related_model.DoesNotExist:
                        pass

            # Handle many-to-many relationships
            for field in ModelClass._meta.many_to_many:
                related_manager = getattr(instance, field.name)
                cloned_related_manager = getattr(cloned_instance, field.name)
                cloned_related_manager.set(related_manager.all())

        return cloned_instance

    # Example usage:
    # instance = YourModel.objects.get(pk=1)
