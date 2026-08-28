"""Submit-time validation: every §6.1 cap lives here, before any paid work."""

import json

import pdfplumber
from django.conf import settings
from rest_framework import serializers
from unstract.agent_kv_schema import SchemaError, compile_schema

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tiff"}
PDF_LIKE = {".pdf"}
IMAGE_LIKE = {".png", ".jpg", ".jpeg", ".tiff"}
EXTRACTION_MODES = ("whole-doc", "per-page")


class SubmitSerializer(serializers.Serializer):
    file = serializers.FileField()
    keys = serializers.CharField()  # JSON string or file part read as string
    document_class = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=256
    )
    key_notes = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=10_000
    )
    calculations = serializers.CharField(required=False, allow_blank=True, default="")
    page_start = serializers.IntegerField(required=False, default=1, min_value=1)
    page_end = serializers.IntegerField(
        required=False, default=None, allow_null=True, min_value=1
    )
    qa = serializers.BooleanField(required=False, default=True)
    challenge = serializers.BooleanField(required=False, default=True)
    extraction_mode = serializers.ChoiceField(
        required=False, choices=EXTRACTION_MODES, default="whole-doc"
    )
    structured_output = serializers.BooleanField(required=False, default=False)
    timeout = serializers.IntegerField(required=False, default=0, min_value=0)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
        max_length=20,
    )
    custom_data = serializers.JSONField(required=False, default=None, allow_null=True)
    webhook_url = serializers.URLField(
        required=False, allow_blank=True, default="", max_length=1024
    )

    compiled = None
    pages_total = None

    def validate_file(self, f):
        name = (f.name or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'; allowed: {sorted(ALLOWED_EXTENSIONS)}"
            )
        max_bytes = settings.AGENT_KV_MAX_FILE_SIZE_MB * 1024 * 1024
        if f.size > max_bytes:
            raise serializers.ValidationError(
                f"File exceeds {settings.AGENT_KV_MAX_FILE_SIZE_MB}MB limit"
            )
        return f

    def validate_calculations(self, v):
        if len(v.encode("utf-8")) > settings.AGENT_KV_MAX_CALCULATIONS_BYTES:
            raise serializers.ValidationError(
                f"calculations exceeds {settings.AGENT_KV_MAX_CALCULATIONS_BYTES} bytes"
            )
        return v

    def validate_timeout(self, v):
        if v > settings.AGENT_KV_MAX_TIMEOUT_SECONDS:
            raise serializers.ValidationError(
                f"timeout must be 0..{settings.AGENT_KV_MAX_TIMEOUT_SECONDS}"
            )
        return v

    def validate_keys(self, raw):
        # Spec §7.1: `keys` may arrive as an inline JSON string OR a file part.
        # DRF hands a file part to CharField as the UploadedFile object's repr,
        # so the view normalizes: SubmitView reads a file-typed `keys` part into
        # a string BEFORE constructing the serializer (see Task 8 Step 7 note).
        if len(raw.encode("utf-8")) > settings.AGENT_KV_MAX_SCHEMA_BYTES:
            raise serializers.ValidationError("keys schema too large")
        try:
            spec = json.loads(raw)
        except (ValueError, TypeError) as e:
            raise serializers.ValidationError(f"keys is not valid JSON: {e}")
        try:
            self.compiled = compile_schema(spec)
        except SchemaError as e:
            raise serializers.ValidationError(str(e))
        return spec

    def validate(self, data):
        start, end = data.get("page_start", 1), data.get("page_end")
        if end is not None and end < start:
            raise serializers.ValidationError(
                {"page_end": "page_end must be >= page_start"}
            )
        f = data["file"]
        ext = "." + f.name.lower().rsplit(".", 1)[-1]
        if ext in PDF_LIKE:
            try:
                with pdfplumber.open(f) as pdf:
                    self.pages_total = len(pdf.pages)
            except Exception:
                raise serializers.ValidationError({"file": "Unreadable PDF"})
            finally:
                f.seek(0)
            if self.pages_total > settings.AGENT_KV_MAX_PAGES:
                raise serializers.ValidationError(
                    {
                        "file": f"Document has {self.pages_total} pages; "
                        f"max is {settings.AGENT_KV_MAX_PAGES} (§6.1)"
                    }
                )
        elif ext in IMAGE_LIKE:
            self.pages_total = 1
        # Excel: no page concept pre-OCR (spec §6.1); pages_total stays None,
        # size cap already enforced; the engine enforces the post-OCR cap.
        return data
