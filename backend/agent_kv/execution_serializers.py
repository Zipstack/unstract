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


SUPPORTED_EXTRACTORS = ("kv",)


class KVOptionsSerializer(serializers.Serializer):
    """The `kv` extractor's own knobs (spec §7.1).

    These used to be top-level submit fields. They are extractor-scoped now
    because they are meaningless to any other extractor -- `qa` and `challenge`
    describe the KV agent pipeline, not "the request".
    """

    qa = serializers.BooleanField(required=False, default=True)
    challenge = serializers.BooleanField(required=False, default=True)
    extraction_mode = serializers.ChoiceField(
        required=False, choices=EXTRACTION_MODES, default="whole-doc"
    )
    structured_output = serializers.BooleanField(required=False, default=False)
    calculations = serializers.CharField(required=False, allow_blank=True, default="")
    document_class = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=256
    )
    key_notes = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=10_000
    )

    def validate_calculations(self, v):
        if v and not settings.AGENT_KV_CALCULATIONS_ENABLED:
            raise serializers.ValidationError(
                "calculations is not available on this deployment yet"
            )
        if len(v.encode("utf-8")) > settings.AGENT_KV_MAX_CALCULATIONS_BYTES:
            raise serializers.ValidationError(
                f"calculations exceeds {settings.AGENT_KV_MAX_CALCULATIONS_BYTES} bytes"
            )
        return v

    def validate_structured_output(self, v):
        if v and not settings.AGENT_KV_STRUCTURED_OUTPUT_ENABLED:
            raise serializers.ValidationError(
                "structured_output is not available on this deployment yet"
            )
        return v

    def validate(self, data):
        # DRF silently DROPS unknown fields. For per-extractor options that is
        # the wrong default: an option aimed at the wrong extractor (or a typo)
        # would be discarded and the job would run with a silently different
        # configuration than the caller asked for. Reject instead.
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                f"unknown options for extractor 'kv': {sorted(unknown)}"
            )
        return data


class ExtractorSerializer(serializers.Serializer):
    """One entry of the submit's `extractors` array (spec §7.0/§7.1)."""

    name = serializers.CharField()
    keys = serializers.JSONField()
    options = serializers.DictField(required=False, default=dict)

    compiled = None

    def validate_name(self, v):
        if v not in SUPPORTED_EXTRACTORS:
            raise serializers.ValidationError(
                f"unknown extractor '{v}'; supported: {list(SUPPORTED_EXTRACTORS)}"
            )
        return v

    def validate_keys(self, spec):
        # Size is capped on the SERIALIZED form: the cap exists to bound parse
        # and compile cost, and `keys` arrives here already parsed out of the
        # `extractors` JSON.
        if len(json.dumps(spec).encode("utf-8")) > settings.AGENT_KV_MAX_SCHEMA_BYTES:
            raise serializers.ValidationError("keys schema too large")
        try:
            self.compiled = compile_schema(spec)
        except SchemaError as e:
            raise serializers.ValidationError(str(e))
        return spec

    def validate(self, data):
        opts = KVOptionsSerializer(data=data.get("options") or {})
        opts.is_valid(raise_exception=True)
        data["options"] = opts.validated_data
        return data


class SubmitSerializer(serializers.Serializer):
    """Submit-time validation: every §6.1 cap lives here, before any paid work.

    The wire format is extractor-scoped (§7.0): per-extractor schema and knobs
    live inside `extractors`, and only fields describing the REQUEST stay top
    level. There is deliberately no alias for the old flat shape.
    """

    file = serializers.FileField()
    extractors = serializers.CharField()  # JSON array string, or a file part
    # Job-level: the page range drives the shared OCR pass and the §6.1 page
    # cap, so it cannot differ between extractors reading the same document.
    page_start = serializers.IntegerField(required=False, default=1, min_value=1)
    page_end = serializers.IntegerField(
        required=False, default=None, allow_null=True, min_value=1
    )
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

    #: ``{extractor_name: compiled schema}`` -- populated during validation.
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

    def validate_timeout(self, v):
        if v > settings.AGENT_KV_MAX_TIMEOUT_SECONDS:
            raise serializers.ValidationError(
                f"timeout must be 0..{settings.AGENT_KV_MAX_TIMEOUT_SECONDS}"
            )
        return v

    def validate_extractors(self, raw):
        # §7.1: `extractors` may arrive as an inline JSON string OR a file part;
        # SubmitView reads a file-typed part into a string before constructing
        # the serializer, exactly as it did for the old `keys` field.
        if len(raw.encode("utf-8")) > settings.AGENT_KV_MAX_SCHEMA_BYTES:
            raise serializers.ValidationError("extractors payload too large")
        try:
            entries = json.loads(raw)
        except (ValueError, TypeError) as e:
            raise serializers.ValidationError(f"extractors is not valid JSON: {e}")
        if not isinstance(entries, list) or not entries:
            raise serializers.ValidationError(
                "extractors must be a non-empty JSON array"
            )
        if len(entries) > 1:
            # The FORMAT is being fixed before launch; the fan-out execution is
            # not built (one executor exists, and page images are not shared).
            # Refusing loudly beats accepting a request we would silently run
            # single-extractor.
            raise serializers.ValidationError(
                "multiple extractors are not supported yet; pass exactly one"
            )

        validated, compiled = [], {}
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise serializers.ValidationError(
                    f"extractors[{i}] must be an object"
                )
            ser = ExtractorSerializer(data=entry)
            if not ser.is_valid():
                raise serializers.ValidationError({f"extractors[{i}]": ser.errors})
            validated.append(ser.validated_data)
            compiled[ser.validated_data["name"]] = ser.compiled
        self.compiled = compiled
        return validated

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
