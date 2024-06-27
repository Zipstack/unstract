from typing import Optional

from django.db import models, transaction
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_studio_index_manager.models import IndexManager
from prompt_studio.prompt_studio_output_manager.models import PromptStudioOutputManager
from unstract.sdk.utils.common_utils import CommonUtils


class CloneUtil:
    # @staticmethod
    # def get_unique_fields(model: models.Model) -> list:
    #     unique_fields = set()
    #     for field in model._meta.fields:
    #         if (
    #             not field.primary_key
    #             and not isinstance(field, models.ForeignKey)
    #         ):
    #             unique_fields.add(field.name)
    #     return list(unique_fields)

    @staticmethod
    def customize_field_value(original_value: str) -> str:
        """Customize the field value for unique fields.

        Special handling for filenames with extensions.
        """
        if "." in original_value:
            name, ext = original_value.rsplit(".", 1)
            return f"{name}_copy.{ext}"
        return f"{original_value}_copy"

    @staticmethod
    def clone_model_instance(
        instance: models.Model,
        parent: Optional[models.Model] = None,
        null_fields: Optional[list[str]] = None,
        new_user: Optional[models.Model] = None,
        tool_name: Optional[str] = None,
    ) -> models.Model:
        """Clones a model instance and its related objects recursively,
        assigning a new primary key.

        Takes into account unique constraints by allowing the user to
        provide overrides for unique fields via kwargs.
        """
        skip_fields = [PromptStudioOutputManager, IndexManager]
        ModelClass = instance.__class__
        related_fields = [
            field
            for field in ModelClass._meta.get_fields()
            if field.one_to_many or field.one_to_one
        ]
        if ModelClass in skip_fields:
            return None
        # Get the unique fields for the instance
        # unique_fields = CloneUtil.get_unique_fields(ModelClass)  # type: ignore

        # Clone the instance without primary key and unique fields
        cloned_instance = ModelClass(
            **{
                field.name: getattr(instance, field.name)
                for field in ModelClass._meta.fields
                if not field.primary_key
            }
        )

        # Set the specified field to null
        if null_fields:
            for field_name in null_fields:
                setattr(cloned_instance, field_name, None)

        # Change the user value if specified
        if new_user:
            setattr(cloned_instance, "created_by", new_user)
            setattr(cloned_instance, "modified_by", new_user)
        if tool_name:
            setattr(cloned_instance, "tool_name", tool_name)

        # Save the cloned instance
        # cloned_instance.save()

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
                            related_object, parent=cloned_instance, new_user=new_user
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

    @staticmethod
    def clone_hierachy(
        tool_id: str,
        null_fields: Optional[list[str]] = None,
        new_user: Optional[models.Model] = None,
        tool_name: Optional[str] = None,
    ) -> models.Model:
        try:
            # Fetch the existing custom tool
            original_tool = CustomTool.objects.get(pk=tool_id)
            profile_managers = ProfileManager.objects.filter(
                prompt_studio_tool=original_tool.tool_id
            ).all()
            prompts = ToolStudioPrompt.objects.filter(tool_id=tool_id).all()
            documents = DocumentManager.objects.filter(tool=tool_id).all()

            # Clone the custom tool with the new name
            original_tool.pk = None
            original_tool.created_by = new_user
            original_tool.modified_by = new_user
            # original_tool.parent_id=tool_id
            original_tool.share_id = None
            original_tool.tool_name = tool_name
            original_tool.save()
            new_cloned_tool = CustomTool.objects.get(tool_name=tool_name)

            # Clone ProfileManagers
            profile_manager_mapping = {}
            for profile_manager in profile_managers:
                new_profile_manager_uuid = CommonUtils.generate_uuid()
                original_profile_manager_pk = profile_manager.pk
                profile_manager.pk = new_profile_manager_uuid  # Reset the primary key to create a new instance
                profile_manager.prompt_studio_tool = (
                    new_cloned_tool  # Set foreign key to the new tool
                )
                profile_manager.save()
                profile_manager_mapping[str(original_profile_manager_pk)] = (
                    new_profile_manager_uuid
                )

            # Clone Prompts and Documents
            prompt_mapping = {}
            for prompt in prompts:
                if prompt.profile_manager:
                    linked_profile = profile_manager_mapping.get(
                        str(prompt.profile_manager.profile_id)
                    )
                    prompt.profile_manager = ProfileManager.objects.get(
                        profile_id=linked_profile
                    )
                original_prompt_pk = prompt.pk
                prompt.pk = None  # Reset the primary key to create a new instance
                prompt.tool_id = (
                    new_cloned_tool  # Set foreign key to the new profile manager
                )
                prompt.save()
                prompt_mapping[original_prompt_pk] = prompt

            # Clone Documents related to the Prompt
            for document in documents:
                document_uuid = CommonUtils.generate_uuid()
                document.pk = (
                    document_uuid  # Reset the primary key to create a new instance
                )
                document.tool = new_cloned_tool  # Set foreign key to the new prompt
                document.save()
                new_cloned_tool.output = document_uuid
                new_cloned_tool.save()

            return new_cloned_tool

        except CustomTool.DoesNotExist:
            raise ValueError("The custom tool with the given ID does not exist")
