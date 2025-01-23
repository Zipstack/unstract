# serializers.py
import re

from rest_framework import serializers
from rest_framework.serializers import CharField, ValidationError
from tags.models import Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "description"]


class TagParamsSerializer(serializers.Serializer):
    # Currently limited to 1 tag per request to maintain compatibility with
    # LLM Whisperer integration. Consider increasing the limit once LLM Whisperer
    # supports multiple tags
    MAX_TAGS_ALLOWED = 1
    tags = CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Comma-separated list of tag names (EX:'tag1,tag2-name,tag3_name')",
    )

    def validate_tags(self, value):
        if not value:
            return []

        # Pattern allows letters, numbers, underscores, and hyphens
        # Must start with a letter
        tag_pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

        # Ensure value is a string
        if not isinstance(value, str):
            raise ValidationError("Tags must be a comma-separated string.")

        tags = [tag.strip() for tag in value.split(",") if tag.strip()]

        # Check maximum number of tags
        if len(tags) > self.MAX_TAGS_ALLOWED:
            raise ValidationError(
                f"Maximum '{self.MAX_TAGS_ALLOWED}' tags allowed. "
                f"You provided '{len(tags)}' tags."
            )

        # Validate tags
        for tag in tags:
            if len(tag) > Tag.TAG_NAME_LENGTH:
                raise ValidationError(
                    f"Tag '{tag}' exceeds the maximum length of {Tag.TAG_NAME_LENGTH}."
                )

            if not tag_pattern.match(tag):
                raise ValidationError(
                    f"Tag '{tag}' is invalid. Tags must start with a letter and "
                    "can only contain letters, numbers, underscores, and hyphens."
                )

        return tags
