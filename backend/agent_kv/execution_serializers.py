"""Submit-time validation: every §6.1 cap lives here, before any paid work."""

import json
import logging

import pdfplumber
from django.conf import settings
from rest_framework import serializers

from agent_kv.constants import EXTRACTOR_ROUTES, TABLE_EXTRACTOR_NAME, V1_EXTRACTOR_NAME
from unstract.agent_kv_schema import SchemaError, compile_schema
from unstract.core.network.ssrf import webhook_url_refusal
from unstract.sdk1.constants import AdapterTypes

logger = logging.getLogger(__name__)

# Images are deliberately ABSENT, and that is a cross-repo contract, not an
# oversight. The cloud engine's `_build_agent_graph` (agentic_kv
# kv_extractor.py) treats only `.pdf/.xlsx/.xls` as a document; anything else
# takes a branch that skips `document_processor` entirely, and
# `ImageLoader.load_pages` -- the only thing that would populate pages for an
# image -- has no call site anywhere in the plugin (the engine's own comment
# there says images are "out of P2 scope").
#
# Accepting them here anyway failed OPEN: an image dispatched normally with
# `pages_total=1`, every key came back not-found, and the job returned
# `success: true` with a page billed. Refusing at submit is the honest
# behaviour until the engine side is wired; re-add them in the same change that
# gives `load_pages` a call site, not before.
ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}
PDF_LIKE = {".pdf"}
EXTRACTION_MODES = ("whole-doc", "per-page")


# Derived, not repeated: the result and status documents key their payloads by
# these names, so a literal here that no route/stage list knows about would let
# the serializer accept a name the responses file under something else.
SUPPORTED_EXTRACTORS = tuple(EXTRACTOR_ROUTES)


#: Sentinel for an extractor that needs no deployment flag.
_UNGATED = object()

#: Distinct from `_UNGATED`: "nobody decided", which refuses. Keeping them
#: separate is the whole point -- one sentinel for both made a forgotten entry
#: indistinguishable from a deliberate no-gate decision.
_NO_DECISION = object()

#: Which setting, if any, gates each ROUTED extractor's acceptance at submit.
#:
#: A TABLE rather than an `if`, for one reason: `constants.py`'s
#: add-an-extractor checklist names "its entry in the acceptance gate" as a
#: step, and an `if` on one hard-coded name gives that step nowhere to go. An
#: earlier revision was exactly that `if`, subtracting `V1_EXTRACTOR_NAME` --
#: so a third extractor was accepted by DEFAULT the moment it was routed,
#: which is verbatim the 202-into-an-undrained-queue shape
#: `settings/base.py` calls the worst available.
#:
#: `_UNGATED` is explicit, not an omission: `table` ships accepted everywhere
#: and says so here. `test_every_routed_extractor_has_a_gate_entry` derives
#: the requirement from `EXTRACTOR_ROUTES`, the way the queue wiring and the
#: billing backstop already do, so adding a route without deciding its gate
#: fails a test rather than silently defaulting to open.
_EXTRACTOR_ENABLE_FLAGS: dict[str, object] = {
    V1_EXTRACTOR_NAME: "AGENT_KV_KV_EXTRACTOR_ENABLED",
    TABLE_EXTRACTOR_NAME: _UNGATED,
}


#: Wiring faults below are static properties of `_EXTRACTOR_ENABLE_FLAGS`, not
#: of a request, but `enabled_extractors()` is called per submit -- so logging
#: them unguarded emitted one ERROR per request, unbounded, straight into
#: Sentry at request rate. Keyed by (extractor, kind) so a second, different
#: fault is still reported. Same reasoning as `tasks._CAPS_LOGGED`, which this
#: PR added for an equivalent operator message.
_WIRING_FAULTS_LOGGED: set[tuple[str, str]] = set()


def _log_wiring_fault_once(kind: str, name: str, *args) -> None:
    key = (name, kind)
    if key in _WIRING_FAULTS_LOGGED:
        return
    _WIRING_FAULTS_LOGGED.add(key)
    logger.error(*args)


def enabled_extractors() -> tuple[str, ...]:
    """The routed extractors this deployment will ACCEPT at submit.

    `SUPPORTED_EXTRACTORS` is what is ROUTED -- it says where an extractor's
    work would be dispatched. That is not the same question as whether anything
    DRAINS the queue it names, and the backend cannot see the worker fleet's
    subscription list: `SubmitView`'s `get_plugin("agent_kv")` probe is
    per-deployment, so it is already truthy wherever `table` shipped and tells
    us nothing about `kv`.

    Read per call rather than at import, so a deployment's setting -- and a
    test's `override_settings` -- is the thing that decides, not the order the
    module happened to be imported in.
    """
    enabled = []
    for name in SUPPORTED_EXTRACTORS:
        # One lookup, and a MISSING entry refuses. An earlier version used
        # `.get(name, _UNGATED)`, which made the no-decision case accept
        # everywhere -- and because `or` short-circuits, the `[name]` lookup
        # that would have raised was unreachable. That is the
        # 202-into-an-undrained-queue shape this table exists to prevent, so
        # the structure has to carry it rather than the derived test alone.
        gate = _EXTRACTOR_ENABLE_FLAGS.get(name, _NO_DECISION)
        if gate is _NO_DECISION:
            _log_wiring_fault_once(
                "no-decision",
                name,
                "agent_kv: extractor %r is routed but has no entry in "
                "_EXTRACTOR_ENABLE_FLAGS; refusing it at submit. Add a setting "
                "name to gate it, or _UNGATED to accept it everywhere.",
                name,
            )
            continue
        if gate is _UNGATED:
            enabled.append(name)
            continue
        # `getattr(settings, gate, False)` conflated two different things, one
        # level below the conflation `_NO_DECISION` was introduced to end: a
        # setting this deployment does not define read exactly like a flag
        # deliberately set false. The operator then sets the variable, nothing
        # changes, and the refusal message tells them the extractor "is not
        # enabled" -- which is the opposite of the truth, because they did
        # enable it.
        #
        # A derived test cannot close this: `override_settings` FABRICATES the
        # attribute on the settings object whether or not the settings module
        # defines it, so every `@override_settings(AGENT_KV_..._ENABLED=...)`
        # case here passes against a settings module that never declares the
        # name. Verified by probe. So the check has to be at runtime.
        if not hasattr(settings, gate):
            _log_wiring_fault_once(
                "undefined-setting",
                name,
                "agent_kv: extractor %r is gated on setting %r, which this "
                "deployment's settings do not define; refusing it at submit. "
                "This is a wiring bug, NOT the operator's flag being off -- "
                "setting %s in the environment will not change it.",
                name,
                gate,
                gate,
            )
            continue
        if getattr(settings, gate):
            enabled.append(name)
    return tuple(enabled)


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


class TableOptionsSerializer(serializers.Serializer):
    """The `table` extractor's own knobs (spec §7.1).

    Deliberately a subset of what the IDE path accepts: `output_path` and the
    IDE callback hints (`prompt_key`, `doc_name`) are meaningless on the blind
    API, and `enable_highlight` has no consumer there.

    **`enable_header_mapping` changes the result shape.** With it off, the
    engine returns `output.tables` as a flat list of row dicts. With it on, the
    engine wraps them as `{"header_mapping": ..., "rows": [...]}`
    (`runner.py:1712`; the executor's own enrichment path unwraps the same
    shape at `executor.py:577`). The API returns whichever the caller asked
    for, unchanged -- so a client that sets this flag must read `.rows`.
    """

    instructions = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=10_000
    )
    json_structure = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=100_000
    )
    enable_header_mapping = serializers.BooleanField(required=False, default=False)
    correct_number_separators = serializers.BooleanField(required=False, default=False)
    number_format = serializers.ChoiceField(
        required=False, choices=("US", "EU"), default="US"
    )

    def validate(self, data):
        # Same reason KVOptionsSerializer rejects unknowns: DRF drops them
        # silently, so an option aimed at the wrong extractor would be
        # discarded and the job would run with a configuration the caller
        # never asked for.
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                f"unknown options for extractor '{TABLE_EXTRACTOR_NAME}': "
                f"{sorted(unknown)}"
            )
        return data


class TableKeysSerializer(serializers.Serializer):
    """The `table` extractor's `keys`.

    The wire format gives every extractor a `keys` member; for the table
    extractor the thing being asked for is a table, named by `target_table`
    (the engine's one required extraction parameter).
    """

    target_table = serializers.CharField(max_length=256)

    def validate(self, data):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                f"unknown keys for extractor '{TABLE_EXTRACTOR_NAME}': {sorted(unknown)}"
            )
        return data


# Each extractor's own validators. Keyed by the same names as EXTRACTOR_ROUTES;
# `test_every_supported_extractor_has_a_route_stage_list_and_options_serializer`
# keeps the three tables in step.
_OPTIONS_SERIALIZERS = {
    V1_EXTRACTOR_NAME: KVOptionsSerializer,
    TABLE_EXTRACTOR_NAME: TableOptionsSerializer,
}


class _ThreeRoleAdaptersSerializer(serializers.Serializer):
    """Shared base: the three platform adapter roles both extractors run on.

    `extractor_name` is only used to name the extractor in the unknown-field
    error, so a knob aimed at the wrong extractor says which one it was aimed
    at. Subclasses set it; the field set and the validate() below are
    identical, because the two engines need the same three roles for the same
    reasons (see `TableAdaptersSerializer` for those reasons in full).
    """

    extractor_name = ""

    llm = serializers.UUIDField()
    lite_llm = serializers.UUIDField()
    x2text = serializers.UUIDField()

    def validate(self, data):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                f"unknown adapters for extractor '{self.extractor_name}': "
                f"{sorted(unknown)}"
            )
        return data


class TableAdaptersSerializer(_ThreeRoleAdaptersSerializer):
    """The platform adapters the `table` extractor runs on.

    **Why the caller names adapters rather than the operator configuring env
    vars.** The engine needs two LLMs and an OCR source. The IDE table path
    resolves all three from platform adapter instances the user configured
    (`agentic_table/executor.py` -> `LLM(adapter_instance_id=...)`,
    `X2Text(adapter_instance_id=...)`), and this API now does the same. That
    reverses spec D6, which specified system-level env configuration and "no
    end-user model control" -- a deliberate reversal, recorded here and in
    `docs/agent-kv-api.md`: the consumers are existing customers with
    accounts, so they already own adapters, and letting them choose puts model
    selection and LLM spend on the account that benefits from it.

    Field names follow the platform convention for naming adapters by ROLE,
    not by id: `prompt_profile_manager_v2.ProfileManager` declares `llm`,
    `x2text`, `embedding_model`, `vector_store`. Hence `llm` / `lite_llm` /
    `x2text` rather than `llm_adapter_id` and friends.

    `lite_llm` is separate because the engine uses a cheaper model for
    per-page presence detection and the advanced one for structure and
    extraction; collapsing them would silently multiply the cost of the
    highest-volume stage.
    """

    extractor_name = TABLE_EXTRACTOR_NAME


class KVAdaptersSerializer(_ThreeRoleAdaptersSerializer):
    """The platform adapters the `kv` extractor runs on.

    Identical to the table extractor's three roles, and for the same reason:
    the KV engine needs an advanced LLM, a cheaper one for per-page work, and
    an OCR source. The rationale in `TableAdaptersSerializer` applies verbatim.

    **The KV path was env-credentialed until the adapter migration**, on one
    operator LLM key and one operator LLMWhisperer key shared by every org.
    It now resolves the caller's own adapters exactly as the table path does,
    which is what lets both extractors live behind one API with one selector
    rather than two credential models. The executor enforces the same three
    roles on its side (`agentic_kv.constants.ParamKeys.REQUIRED_ADAPTERS`) and
    fails the job naming whichever is missing; this serializer is what turns
    that into a 400 at submit instead, before a concurrency slot is taken and
    before staging is billed.
    """

    extractor_name = V1_EXTRACTOR_NAME


#: Each extractor's own `adapters` validator, and which `AdapterTypes` each
#: role must be. An extractor absent from this table takes no adapters at all
#: and a supplied `adapters` block is a 400 (`_validated_adapter_shape`).
#:
#: Both shipped extractors are present, which is the point: there is no longer
#: one env-credentialed extractor and one adapter-credentialed one. `kv` joined
#: this table with the adapter migration. Note what the refusal actually was
#: while it was absent: NOT "takes no adapters" -- `kv` was not in
#: `EXTRACTOR_ROUTES` either, so `SUPPORTED_EXTRACTORS` was `('table',)` and
#: `validate_name` rejected the entry as an unknown extractor before
#: `_validated_adapter_shape` ever ran. The engine ran on operator credentials
#: for callers who had it enabled by other means.
#:
#: The roles here must stay a superset of what each executor requires, or a
#: submit passes and the job fails mid-run: `agentic_kv` enforces
#: `ParamKeys.REQUIRED_ADAPTERS` and `agentic_table` its `API_REQUIRED_ADAPTERS`.
_ADAPTERS_SERIALIZERS = {
    V1_EXTRACTOR_NAME: (
        KVAdaptersSerializer,
        {
            "llm": AdapterTypes.LLM,
            "lite_llm": AdapterTypes.LLM,
            "x2text": AdapterTypes.X2TEXT,
        },
    ),
    TABLE_EXTRACTOR_NAME: (
        TableAdaptersSerializer,
        {
            "llm": AdapterTypes.LLM,
            "lite_llm": AdapterTypes.LLM,
            "x2text": AdapterTypes.X2TEXT,
        },
    ),
}


#: Each extractor's own `keys` validator. An extractor absent from this table
#: falls through to the schema compiler, which is `kv`'s contract: its `keys` IS
#: a compiled schema rather than a fixed set of fields.
_KEYS_SERIALIZERS = {
    TABLE_EXTRACTOR_NAME: TableKeysSerializer,
}


def _validated_adapter_shape(name: str, supplied) -> dict:
    """Validate an extractor's `adapters` block SHAPE only. No database.

    Returns `{role: "<uuid>"}`, or `{}` for an extractor that takes none.

    Deliberately split from the tenancy check. This runs in the serializer, so
    it must stay free of the ORM -- `test_submit_serializer.py` is a unit suite
    with no database, and an adapter lookup here would make every submit test
    require one. What it does check is everything that needs no database:
    presence, that each id parses as a UUID, and that no unknown role was sent.

    **Ownership and type are checked in the VIEW**
    (`execution_views._resolved_adapters`), because they need the Bearer key's
    organization -- the same reason `_subscription_denial` lives there. Both
    still run before anything is staged or billed.
    """
    entry = _ADAPTERS_SERIALIZERS.get(name)
    if entry is None:
        if supplied:
            raise serializers.ValidationError(
                {"adapters": f"extractor '{name}' takes no adapters"}
            )
        return {}

    adapters_cls, _expected_types = entry
    ser = adapters_cls(data=supplied if isinstance(supplied, dict) else {})
    ser.is_valid(raise_exception=True)
    return {role: str(value) for role, value in ser.validated_data.items()}


class ExtractorSerializer(serializers.Serializer):
    """One entry of the submit's `extractors` array (spec §7.0/§7.1)."""

    name = serializers.CharField()
    keys = serializers.JSONField()
    #: Sibling of `keys`/`options`, not nested inside them. These are the
    #: RESOURCES the extractor runs on, which `ProfileManager` likewise holds
    #: as fields on the owning object rather than inside a knobs blob -- and
    #: keeping them out of `options` leaves that member optional.
    adapters = serializers.DictField(required=False, default=dict)
    options = serializers.DictField(required=False, default=dict)

    def validate_name(self, v):
        enabled = enabled_extractors()
        if v in enabled:
            return v
        # Routed but not enabled here. Say so rather than reporting it as
        # unknown: "unknown" sends an integrator looking for a typo, and the
        # deployment -- not the request -- is what has to change.
        if v in SUPPORTED_EXTRACTORS:
            raise serializers.ValidationError(
                f"extractor '{v}' is not enabled on this deployment"
            )
        raise serializers.ValidationError(
            f"unknown extractor '{v}'; supported: {list(enabled)}"
        )

    def _validated_keys(self, name: str, spec):
        """Validate `keys` for the extractor named by the VALIDATED `name`.

        Not a `validate_keys` field validator, deliberately. That ran before
        object-level validation and branched on raw ``self.initial_data["name"]``
        -- while ``validate_name`` saw the value DRF had already trimmed
        (``CharField.trim_whitespace`` defaults True). So the extractor's
        identity was decided twice, under two different values:
        ``{"name": " table ", ...}`` passed the name check as ``table`` and then
        took the **kv** branch here, never running ``TableKeysSerializer``. A
        kv-shaped payload like ``{"target_table": {"description": "x"}}``
        compiles cleanly as a KV schema, so the submit returned **202** and
        dispatched to ``agentic_table`` with a `target_table` that is a dict
        rather than the string the binding requires -- the job staged, billed
        and then failed at the executor.

        Branching on `data["name"]` in ``validate()`` means the name is trimmed
        and already checked against ``enabled_extractors()`` exactly once.
        """
        keys_cls = _KEYS_SERIALIZERS.get(name)
        if keys_cls is not None:
            keys = keys_cls(data=spec if isinstance(spec, dict) else {})
            keys.is_valid(raise_exception=True)
            return keys.validated_data

        # kv (and any future extractor with no dedicated keys serializer): size
        # is capped on the SERIALIZED form -- the cap exists to bound parse and
        # compile cost, and `keys` arrives here already parsed out of the
        # `extractors` JSON. ensure_ascii=False so this measures the SAME bytes
        # the outer `extractors` cap measured.
        serialized = json.dumps(spec, ensure_ascii=False).encode("utf-8")
        if len(serialized) > settings.AGENT_KV_MAX_SCHEMA_BYTES:
            raise serializers.ValidationError({"keys": "keys schema too large"})
        # Called for what it REFUSES, not for what it returns. The
        # `CompiledSchema` used to be stashed on the serializer and collected
        # into a `{name: compiled}` dict by `SubmitSerializer`, which no
        # non-test code ever read: `dispatch_job` sends `schema=entry["keys"]`,
        # the raw dict, and the engine re-compiles it on its own (see the
        # docstring on `compile.py` -- the caps are a submit-time gate, not an
        # invariant the engine re-checks). Plumbing the compiled form through
        # instead is not an option the queue allows: it would have to survive
        # JSON round-tripping to the executor, which is exactly why the engine
        # recompiles. So the dead attribute is gone rather than left to read as
        # plumbing that exists. What this call is for is the 400 below.
        try:
            compile_schema(spec)
        except SchemaError as e:
            raise serializers.ValidationError({"keys": str(e)})
        return spec

    def validate(self, data):
        # Same reason the options block rejects unknowns, one level up: DRF drops
        # unrecognised keys, so `"option"` or `"Options"` for `"options"` would
        # be discarded whole, `options` would default to {}, and the job would
        # run with qa=True/challenge=True -- roughly double the LLM spend the
        # caller asked for, with a 202 and no indication anything was ignored.
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                f"unknown keys on extractor entry: {sorted(unknown)}"
            )
        name = data["name"]
        data["keys"] = self._validated_keys(name, data.get("keys"))
        opts_cls = _OPTIONS_SERIALIZERS[name]
        opts = opts_cls(data=data.get("options") or {})
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

    def validate_webhook_url(self, value):
        """Refuse at submit what the sink will refuse at delivery.

        `URLField` alone accepts `http://`, `localhost` and private address
        literals, none of which this API will ever dial: `send_webhook` is
        called without `allow_http`, so the sink allows https to public hosts
        only. The caller therefore got a 202 and a webhook that never arrived,
        with nothing in the response contradicting the "https-only" promise in
        the docs -- and on the cancel path `agent_kv_cancelled` treats the
        refusal as a delivery failure and burns its whole retry budget on a
        URL that cannot work.

        `resolve=False`, matching `notification_v2.serializers`: DNS has no
        timeout and this runs on the request thread, so a hostname pointing
        inward is accepted here and refused at the sink, which does resolve.
        The syntactic checks -- scheme, credentials in the URL, parser
        disagreement, address literals -- all still run.
        """
        if not value:
            return value
        if settings.AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE:
            # The same test/dev waiver the delivery sink reads. Both sides
            # must honour it or they disagree: with the check only at submit,
            # the e2e webhook scenario 400s before a job exists; with it only
            # at the sink, this validation is the thing that breaks it. Unset
            # in production.
            return value
        reason = webhook_url_refusal(value, allowed_schemes=("https",), resolve=False)
        if reason is not None:
            raise serializers.ValidationError(
                "webhook_url must be an https URL on a public host " f"({reason})"
            )
        return value

    #: Measured page count of the uploaded document. None for Excel, which has
    #: no pre-OCR page concept. This is what metering and the status document
    #: report, and it is NOT what the page cap is compared against.
    pages_total = None
    #: How many pages the request actually asks to process, after `page_start` /
    #: `page_end` are applied. This is what the cap bounds. None for Excel.
    pages_selected = None

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
        except RecursionError:
            # NOT a ValueError, so the clause above does not catch it: it is a
            # RuntimeError subclass, and an uncaught one here is a 500 on a
            # request the caller controls entirely. `[` repeated a few thousand
            # times exhausts the decoder's recursion limit while occupying a
            # tiny fraction of AGENT_KV_MAX_SCHEMA_BYTES (256 KiB), so the byte
            # cap above is no defence at all -- the cheapest possible input
            # reaches it (Greptile P2).
            #
            # Reported as a validation error rather than re-raised, because it
            # IS one: the payload is malformed for this endpoint's purposes,
            # and the caller can act on the message. Depth is not named as a
            # number because the limit is the interpreter's, not ours.
            raise serializers.ValidationError("extractors is nested too deeply to parse")
        if not isinstance(entries, list) or not entries:
            raise serializers.ValidationError("extractors must be a non-empty JSON array")
        if len(entries) > 1:
            # The FORMAT is being fixed before launch; the fan-out execution is
            # not built (one executor exists, and page images are not shared).
            # Refusing loudly beats accepting a request we would silently run
            # single-extractor.
            raise serializers.ValidationError(
                "multiple extractors are not supported yet; pass exactly one"
            )

        validated = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise serializers.ValidationError(f"extractors[{i}] must be an object")
            ser = ExtractorSerializer(data=entry)
            if not ser.is_valid():
                raise serializers.ValidationError({f"extractors[{i}]": ser.errors})
            data = ser.validated_data
            try:
                data["adapters"] = _validated_adapter_shape(
                    data["name"], data.get("adapters")
                )
            except serializers.ValidationError as e:
                raise serializers.ValidationError(
                    {f"extractors[{i}]": e.detail}
                ) from None
            validated.append(data)
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
            if start > self.pages_total:
                raise serializers.ValidationError(
                    {
                        "page_start": f"page_start {start} is past the end of a "
                        f"{self.pages_total}-page document"
                    }
                )
            # The cap is on the DOCUMENT, not on the selected range, and the
            # reason is billing rather than tidiness.
            #
            # This briefly compared `pages_selected` instead, on the premise
            # that "pages 1-5 of a 400-page PDF is five pages of OCR". That
            # premise is false. The engine renders EVERY page
            # (`convert_pdf_to_images(file_content, dir)`) and OCRs the whole
            # file -- `X2Text.process` takes `input_file_path` and no range at
            # all -- and `load_pages(starting_page=, ending_page=)` filters
            # afterwards, choosing only which rendered pages the agents look
            # at. So pages 1-5 of a 400-page document costs 400 pages of OCR
            # and is billed for 400.
            #
            # It also disagreed with the worker, which has always refused on
            # `pages_total` (cloud `api_binding.py`). The caller got a 202,
            # a concurrency slot and a staged upload, and then a failure --
            # the worst of both, since the refusal still arrived but only
            # after the request looked accepted. Caught in review on #2317 /
            # unstract-cloud#1828.
            #
            # `pages_selected` is still computed: it is the honest count of
            # what will be EXTRACTED, and the message below uses it to explain
            # why a small range was refused anyway.
            last_page = self.pages_total if end is None else min(end, self.pages_total)
            self.pages_selected = last_page - start + 1
            if self.pages_total > settings.AGENT_KV_MAX_PAGES:
                raise serializers.ValidationError(
                    {
                        "file": f"Document has {self.pages_total} pages; max is "
                        f"{settings.AGENT_KV_MAX_PAGES} (§6.1). A page range does "
                        "not reduce this: the whole document is OCR'd and billed "
                        "regardless of page_start/page_end"
                    }
                )
        # Excel: no page concept pre-OCR (spec §6.1); pages_total stays None,
        # size cap already enforced; the engine enforces the post-OCR cap.
        return data
