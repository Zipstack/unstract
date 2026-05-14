"""Sanitized serializer base classes.

`SanitizedSerializerMixin` attaches `validate_no_html_tags` to every writable
`CharField` on the serializer, so new serializers are protected from stored
XSS without per-field wiring. Opt out per-serializer via
`Meta.html_safe_fields = (...)` for fields that legitimately accept HTML-like
content (e.g. prompt text, regex literals).

Use the pre-mixed `ModelSerializer` / `Serializer` / `HyperlinkedModelSerializer`
classes instead of importing from `rest_framework` directly:

    from utils.serializer import ModelSerializer

    class FooSerializer(ModelSerializer):
        class Meta:
            model = Foo
            fields = ["name", "description", "prompt"]
            html_safe_fields = ("prompt",)  # opt-out
"""

from functools import partial

from rest_framework import serializers as drf

from utils.input_sanitizer import validate_no_html_tags


class SanitizedSerializerMixin:
    """Attach `validate_no_html_tags` to every writable CharField."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meta = getattr(self, "Meta", None)
        exempt = set(getattr(meta, "html_safe_fields", ()) or ())
        for name, field in self.fields.items():
            if name in exempt or field.read_only:
                continue
            if isinstance(field, drf.CharField):
                # partial binds the field name at iteration time, avoiding the
                # late-binding closure trap of a bare lambda.
                field.validators.append(partial(validate_no_html_tags, field_name=name))


class ModelSerializer(SanitizedSerializerMixin, drf.ModelSerializer):
    pass


class Serializer(SanitizedSerializerMixin, drf.Serializer):
    pass


class HyperlinkedModelSerializer(
    SanitizedSerializerMixin, drf.HyperlinkedModelSerializer
):
    pass
