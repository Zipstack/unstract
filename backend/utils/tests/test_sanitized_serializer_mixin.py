import pytest
from rest_framework import serializers as drf
from rest_framework.exceptions import ValidationError

from utils.serializer import (
    HyperlinkedModelSerializer,
    ModelSerializer,
    SanitizedSerializerMixin,
    Serializer,
)


class PlainSerializer(Serializer):
    name = drf.CharField(max_length=100)
    description = drf.CharField(max_length=500, allow_blank=True)
    count = drf.IntegerField(required=False)


class WithOptOutSerializer(Serializer):
    name = drf.CharField(max_length=100)
    prompt = drf.CharField()

    class Meta:
        html_safe_fields = ("prompt",)


class WithReadOnlySerializer(Serializer):
    name = drf.CharField(max_length=100)
    computed = drf.CharField(read_only=True)


class TestSanitizedSerializerMixin:
    def test_rejects_html_in_writable_charfield(self):
        s = PlainSerializer(data={"name": "<script>alert(1)</script>", "description": ""})
        assert not s.is_valid()
        assert "name" in s.errors

    def test_rejects_html_in_description(self):
        s = PlainSerializer(data={"name": "ok", "description": "<img onerror=x>"})
        assert not s.is_valid()
        assert "description" in s.errors

    def test_clean_input_passes(self):
        s = PlainSerializer(data={"name": "My Workflow", "description": "Plain text."})
        assert s.is_valid(), s.errors

    def test_does_not_touch_non_charfield(self):
        s = PlainSerializer(data={"name": "ok", "description": "", "count": 42})
        assert s.is_valid(), s.errors

    def test_each_field_gets_its_own_validator(self):
        """Default-arg closure capture: the field_name in the error must match the offender."""
        s = PlainSerializer(data={"name": "ok", "description": "<x>"})
        assert not s.is_valid()
        assert "description" in s.errors
        msg = str(s.errors["description"][0])
        assert "description" in msg.lower()

    def test_html_safe_fields_opts_out(self):
        s = WithOptOutSerializer(
            data={"name": "ok", "prompt": "<thinking>step 1</thinking>"}
        )
        assert s.is_valid(), s.errors

    def test_html_safe_fields_does_not_leak_to_other_fields(self):
        s = WithOptOutSerializer(
            data={"name": "<script>", "prompt": "<thinking>step 1</thinking>"}
        )
        assert not s.is_valid()
        assert "name" in s.errors

    def test_read_only_field_is_naturally_exempt(self):
        s = WithReadOnlySerializer(data={"name": "ok"})
        assert s.is_valid(), s.errors

    def test_missing_meta_does_not_break(self):
        class NoMetaSerializer(Serializer):
            name = drf.CharField()

        s = NoMetaSerializer(data={"name": "ok"})
        assert s.is_valid(), s.errors

    def test_meta_without_html_safe_fields_does_not_break(self):
        class MetaWithoutAttrSerializer(Serializer):
            name = drf.CharField()

            class Meta:
                pass

        s = MetaWithoutAttrSerializer(data={"name": "<script>"})
        assert not s.is_valid()
        assert "name" in s.errors

    def test_pre_mixed_classes_inherit_mixin(self):
        assert issubclass(ModelSerializer, SanitizedSerializerMixin)
        assert issubclass(Serializer, SanitizedSerializerMixin)
        assert issubclass(HyperlinkedModelSerializer, SanitizedSerializerMixin)

    def test_rejects_javascript_protocol(self):
        s = PlainSerializer(data={"name": "javascript:alert(1)", "description": ""})
        assert not s.is_valid()
        assert "name" in s.errors

    def test_rejects_event_handler(self):
        s = PlainSerializer(data={"name": "onclick=alert(1)", "description": ""})
        assert not s.is_valid()
        assert "name" in s.errors

    def test_validation_raises_validation_error_type(self):
        """End-to-end: raise_exception path surfaces a DRF ValidationError."""
        s = PlainSerializer(data={"name": "<script>", "description": ""})
        with pytest.raises(ValidationError):
            s.is_valid(raise_exception=True)
