"""The committed spec is the contract the published clients are generated from.

A route, serializer or schema-annotation change that is not regenerated ships a
spec describing an API the server no longer serves, so drift fails here rather
than in a client repo.

Drift alone would pass on a spec that is uniformly wrong, so the tests below
also anchor the parts a client breaks on -- the upload encoding, the nullable
result, the error body -- to the code that produces them.
"""

import dataclasses
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import resolve, reverse
from drf_spectacular.drainage import warn
from drf_spectacular.generators import SchemaGenerator
from middleware.exception import drf_logging_exc_handler
from platform_api.models import ApiKeyPermission
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.test import APIRequestFactory
from utils.user_context import UserContext
from workflow_manager.endpoint_v2.dto import FileExecutionResult
from workflow_manager.workflow_v2.dto import ExecutionResponse

from api_v2.api_deployment_views import APIDeploymentViewSet
from api_v2.management.commands.generate_docstudio_spec import (
    DEFAULT_OUT,
    DOWNSTREAM,
    ORG_SEGMENT,
    REGENERATE,
    SpecGenerationFailed,
    render_spec,
)
from api_v2.serializers import APIExecutionResponseSerializer

#: Keys under a path item that are operations. The rest -- `parameters`,
#: `summary`, vendor extensions -- describe the path, not a call.
_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

#: Documented on a file result but absent from the DTO: the workflow copies it
#: up from the extraction metadata when the request asks for it.
_PROMOTED_FILE_RESULT_FIELDS = {"extracted_text"}

#: Responses whose published example already contradicted its schema before
#: this check existed. All three are the deployment operations declaring a
#: non-error body for a status the standardized-errors schema class also
#: injects a handler-shaped example for. Recorded rather than silently skipped:
#: the check below fails on any *new* instance, and this list is the debt.
#: Keyed by schema name as well, so that a response later declaring a
#: *different* non-`ErrorResponse` body stops inheriting the suppression.
_KNOWN_EXAMPLE_DIVERGENCES = {
    ("status", "406", "NotAcceptable", "AcknowledgedResponse"),
    ("status", "500", "APIException", "StatusResponse"),
    ("execute", "500", "APIException", "ExecuteResponse"),
}

#: The operations served by an API deployment, as opposed to the platform-key
#: operations that describe the account. They authenticate differently and can
#: fail differently, so several checks below split on this.
DEPLOYMENT_OPERATIONS = {"execute", "status"}

#: The operations a caller can address wrongly, because they take a body or a
#: parameter. The rest cannot answer 400 whatever the caller sends.
REJECTABLE_REQUEST_OPERATIONS = DEPLOYMENT_OPERATIONS | {"list_deployments"}

#: The operations that can refuse a credential they recognise -- a key for
#: another deployment, or for another organisation. Where a key that resolves
#: at all is a key that may proceed, there is no 403 to document.
REFUSABLE_OPERATIONS = DEPLOYMENT_OPERATIONS | {"list_deployments"}


@pytest.fixture(autouse=True)
def _outside_any_request() -> None:
    """Generation reaches the organisation-scoped managers, and the command
    runs with nothing in this thread-local. A value left by an earlier test
    sends them to a database these tests do not open.
    """
    UserContext.set_organization_identifier(None)


def _committed() -> dict:
    return json.loads(DEFAULT_OUT.read_text())


def _schema(name: str) -> dict:
    return _committed()["components"]["schemas"][name]


def _operations(spec: dict) -> list[tuple[str, str, dict]]:
    """Every (path, method, operation) the spec documents.

    The spec grows an endpoint at a time, and a check written against exactly
    one of them fails on the next addition without anything being wrong.
    """
    operations = [
        (path, method, operation)
        for path, path_item in spec["paths"].items()
        for method, operation in path_item.items()
        if method in _METHODS
    ]
    assert operations, "the spec documents no operation at all"
    return operations


def test_committed_spec_matches_the_code() -> None:
    assert DEFAULT_OUT.exists(), f"{DEFAULT_OUT} is missing"
    assert DEFAULT_OUT.read_text() == render_spec(), (
        f"{DEFAULT_OUT} is out of date. Run `{REGENERATE}` from `backend/` and "
        f"commit the result.\n\n{DOWNSTREAM}"
    )


def test_a_generator_diagnostic_fails_generation(monkeypatch) -> None:
    """An operation spectacular could not resolve is published empty rather
    than dropped, so the drift comparison would certify the gap.
    """

    def guessing_generator(self, request=None, public=False) -> dict:
        warn("unable to guess serializer")
        return {"openapi": "3.0.3", "paths": {}}

    monkeypatch.setattr(SchemaGenerator, "get_schema", guessing_generator)

    with pytest.raises(SpecGenerationFailed, match="unable to guess serializer"):
        render_spec()


def test_a_path_outside_the_published_mounts_fails_generation(monkeypatch) -> None:
    """The gate the diff widened, exercised on the branch it protects.

    Widening it from one prefix to two is exactly the edit that could admit
    everything; the accept direction is covered incidentally by every other
    test here, and only this one covers the refusal.
    """

    def off_prefix_generator(self, request=None, public=False) -> dict:
        # Otherwise-valid, so the OpenAPI-validity gate below cannot be what
        # raises: matching on the path alone passed even with the prefix gate
        # removed, because the validity error quotes the instance back.
        return {
            "openapi": "3.0.3",
            "info": {"title": "t", "version": "v1"},
            "paths": {"/private/api/{org_name}/": {}},
        }

    monkeypatch.setattr(SchemaGenerator, "get_schema", off_prefix_generator)

    with pytest.raises(SpecGenerationFailed, match="outside the published mounts"):
        render_spec()


def _routed(path: str) -> str:
    """The path Django's URLconf sees, given a documented one.

    They differ by the organisation segment, which `OrganizationMiddleware`
    strips before routing.
    """
    concrete = path.replace("{org_name}", "ORG").replace("{api_name}", "API")
    return concrete.replace(f"/{ORG_SEGMENT}/", "/")


def test_spec_paths_are_the_urls_the_server_serves() -> None:
    """Resolves the real mount rather than restating it: a spec generated for
    URLs the server does not serve is the failure this file exists to catch.
    """
    served = reverse(
        "api_deployment_execution", kwargs={"org_name": "ORG", "api_name": "API"}
    )
    documented = [_routed(path) for path in _committed()["paths"]]

    assert served.rstrip("/") in [path.rstrip("/") for path in documented]
    for path in documented:
        # Raises Resolver404 if the spec documents a URL nothing answers.
        resolve(path if path.endswith("/") else f"{path}/")


def test_the_listing_is_documented_at_the_url_the_server_serves() -> None:
    """The listing's mount is restated in `deployment_spec_urls` rather than
    selected, so nothing but this holds it to the route it stands for.
    """
    (documented,) = (
        path
        for path, _, operation in _operations(_committed())
        if operation["operationId"] == "list_deployments"
    )

    assert _routed(documented) == reverse("tenant:api_deployment")


def test_the_listing_documents_only_the_method_it_publishes() -> None:
    """The served route also answers POST to create a deployment, which is not
    published; the restated route names one method, and this says which.
    """
    served = resolve(reverse("tenant:api_deployment"))
    assert served.func.cls is APIDeploymentViewSet
    assert served.func.actions["get"] == APIDeploymentViewSet.list.__name__

    (path,) = (
        path
        for path, _, operation in _operations(_committed())
        if operation["operationId"] == "list_deployments"
    )
    assert set(_committed()["paths"][path]) & set(_METHODS) == {"get"}


def test_the_listing_asks_for_the_organisation_it_lists() -> None:
    """The counterpart of `test_the_identity_read_asks_for_no_organisation`.
    The router never sees this segment, so nothing but generation puts it in
    the spec.
    """
    reads = [
        (path, operation)
        for path, _, operation in _operations(_committed())
        if operation["operationId"] == "list_deployments"
    ]

    assert reads
    for path, operation in reads:
        assert ORG_SEGMENT in path, path
        declared = [
            parameter
            for parameter in operation["parameters"]
            if parameter["in"] == "path"
        ]
        assert [parameter["name"] for parameter in declared] == ["org_id"], path
        assert declared[0]["required"] is True, path


def test_the_listed_fields_a_client_reads_are_not_optional() -> None:
    """The model defaults these, so DRF reports them optional for a request
    body. In a response they are always sent, and a client that types them
    nullable makes every caller check a key that is always there.
    """
    listed = _schema("APIDeploymentSummary")

    assert {
        "api_name",
        "api_endpoint",
        "display_name",
        "description",
        "is_active",
    } <= set(listed["required"])


def test_spec_documents_the_deployment_operations() -> None:
    spec = _committed()
    documented = {operation["operationId"] for _, _, operation in _operations(spec)}

    assert {"execute", "status"} <= documented
    assert "deployment" in [tag["name"] for tag in spec["tags"]]


def test_every_operation_names_the_credential_it_takes() -> None:
    """Without this the unset DRF authentication default is published as
    though it were a decision, and no generated client can authenticate.

    Which credential differs by operation -- a deployment key runs a
    deployment, a platform key describes itself -- so what is pinned here is
    that each operation names exactly one, and that the scheme it names is
    declared and is a bearer token.
    """
    spec = _committed()
    schemes = spec["components"]["securitySchemes"]

    for path, method, operation in _operations(spec):
        security = operation["security"]
        assert len(security) == 1, f"{method} {path}"
        (requirement,) = security
        (name,) = requirement
        assert requirement[name] == [], f"{method} {path}"
        assert (schemes[name]["type"], schemes[name]["scheme"]) == (
            "http",
            "bearer",
        ), f"{method} {path}"


def test_the_deployment_operations_take_the_deployment_key() -> None:
    """The credential each operation names is part of its contract, so the
    pairing is pinned rather than left to the loop above.
    """
    for path, method, operation in _operations(_committed()):
        if operation["operationId"] in DEPLOYMENT_OPERATIONS:
            assert operation["security"] == [{"deploymentKey": []}], f"{method} {path}"
        else:
            assert operation["security"] == [{"platformKey": []}], f"{method} {path}"


def test_clients_can_branch_on_every_failure_they_will_see() -> None:
    """Every operation authenticates and can fail on the server, so these two
    are the branches a client needs whatever it is calling.

    403 is not universal: it moved to the deployment check below once `whoami`
    became the first operation that authenticates but cannot refuse. Keeping it
    here would have forced a status the published path can never send.
    """
    for path, method, operation in _operations(_committed()):
        assert {"401", "500"} <= set(operation["responses"]), f"{method} {path}"


def test_operations_document_a_rejected_request_only_where_one_is_possible() -> None:
    """Kept off the universal check above: a request carrying no body and no
    parameter cannot be malformed, not every credential can be refused once it
    is recognised, nothing but the deployment operations names a resource that
    can be missing, and documenting a status an operation cannot return hands
    clients a dead branch.
    """
    for path, method, operation in _operations(_committed()):
        responses = set(operation["responses"])
        operation_id = operation["operationId"]
        assert ("400" in responses) is (
            operation_id in REJECTABLE_REQUEST_OPERATIONS
        ), f"{method} {path}"
        assert ("403" in responses) is (
            operation_id in REFUSABLE_OPERATIONS
        ), f"{method} {path}"
        assert ("404" in responses) is (
            operation_id in DEPLOYMENT_OPERATIONS
        ), f"{method} {path}"


def test_only_the_execution_endpoint_documents_the_statuses_only_it_returns() -> None:
    """Fetching a document and taking a rate-limit slot happen on the execute
    call alone, so declaring them on the status read hands clients branches
    that can never be taken.
    """
    fetch_and_rate_limit = {"413", "429", "502", "504"}
    for _, _, operation in _operations(_committed()):
        declared = fetch_and_rate_limit & set(operation["responses"])
        if operation["operationId"] == "execute":
            assert declared == fetch_and_rate_limit
        else:
            assert not declared


def test_the_one_shot_read_is_documented_where_a_client_will_see_it() -> None:
    """The semantics that a status read destroys the result must reach the
    generated client, not live in a source comment.
    """
    reads = [
        operation
        for _, _, operation in _operations(_committed())
        if operation["operationId"] == "status"
    ]

    assert reads
    for status_op in reads:
        assert "one-shot" in status_op["description"]
        # A pending poll answers 422, so a client that raises on non-2xx needs
        # to be told before it wraps this endpoint in a loop.
        assert "422" in status_op["description"]
        assert status_op["responses"]["406"]["description"].strip()


# What each description asserts about how the server behaves. Prose that makes
# a promise is contract text, and reaches the caller as the client's docstring
# and the CLI's help, so it is pinned like any other part of the contract.
BEHAVIOUR_PROMISED_IN_PROSE = {
    "whoami": ["no organisation segment", "rejected as unauthenticated"],
    "list_deployments": ["not part of this listing", "most recent run first"],
    "execute": [
        "global API deployment key",
        "carrying neither is rejected",
        "`timeout` of -1",
    ],
    "status": ["one-shot", "422"],
}


def test_every_operation_carries_a_summary_a_command_list_can_show() -> None:
    """A generated client headlines its method with the summary, and a CLI
    built from this spec lists each command by it. Without one the listing
    falls back to the operation id, or to nothing at all.
    """
    for path, method, operation in _operations(_committed()):
        summary = operation.get("summary", "")
        assert summary, f"{method} {path}"
        # Long enough to say something, short enough for one terminal row.
        assert 20 <= len(summary) <= 60, f"{method} {path}: {summary}"
        assert not summary.endswith("."), f"{method} {path}: {summary}"
        assert summary != operation["description"], f"{method} {path}"


def test_each_description_still_promises_what_it_promised() -> None:
    """These sentences are the only place a caller learns the behaviour they
    describe, and nothing else fails when one is edited away.
    """
    described = {
        operation["operationId"]: operation["description"]
        for _, _, operation in _operations(_committed())
    }

    assert set(described) == set(BEHAVIOUR_PROMISED_IN_PROSE)
    for operation_id, promises in BEHAVIOUR_PROMISED_IN_PROSE.items():
        for promise in promises:
            assert promise in described[operation_id], f"{operation_id}: {promise}"


def test_documents_are_uploaded_as_binary_not_as_urls() -> None:
    """A bare DRF FileField documents as `format: uri`, which generators turn
    into a string parameter and no multipart upload.
    """
    files = _schema("ExecuteRequest")["properties"]["files"]

    assert files["items"] == {"type": "string", "format": "binary"}


def test_the_result_a_pending_execution_omits_is_documented_nullable() -> None:
    """Both endpoints send `result: null` until the execution finishes, and a
    generated deserialiser iterates that field.
    """
    assert _schema("ExecutionMessage")["properties"]["result"]["nullable"] is True
    assert _schema("StatusResponse")["properties"]["message"]["nullable"] is True


def test_the_documented_response_fields_are_ones_the_code_produces() -> None:
    """`APIExecutionResponseSerializer` builds the live execute response, so a
    field documented here that the DTO no longer carries reaches clients as a
    field the server never sends.
    """
    documented = set(APIExecutionResponseSerializer().get_fields())
    produced = {field.name for field in dataclasses.fields(ExecutionResponse)}

    assert documented <= produced, documented - produced


def test_the_documented_file_result_fields_are_ones_the_code_produces() -> None:
    documented = set(_schema("FileResult")["properties"])
    produced = {
        field.name for field in dataclasses.fields(FileExecutionResult)
    } | _PROMOTED_FILE_RESULT_FIELDS

    assert documented <= produced, documented - produced


def test_the_status_read_documents_the_two_keys_it_returns() -> None:
    """The status view builds its body literally, so the spec is the only
    place the pair is written down.
    """
    status_response = _schema("StatusResponse")

    assert set(status_response["properties"]) == {"status", "message"}
    assert status_response["properties"]["message"]["items"]["$ref"].endswith(
        "/FileResult"
    )


def test_spec_documents_the_identity_operation() -> None:
    spec = _committed()
    documented = {operation["operationId"] for _, _, operation in _operations(spec)}

    assert "whoami" in documented
    assert "identity" in [tag["name"] for tag in spec["tags"]]


def test_the_identity_read_documents_the_keys_it_returns() -> None:
    """The view builds its body literally, so the spec is the only place the
    set is written down.
    """
    whoami = _schema("WhoAmIResponse")
    fields = {"organization_id", "organization_name", "permission", "key_name"}

    assert set(whoami["properties"]) == fields
    # All four are read off a key row that always has them, so a client can
    # treat every one as present rather than guarding each.
    assert set(whoami["required"]) == fields


def test_the_documented_permission_tiers_are_the_ones_the_model_defines() -> None:
    """A tier added to the model but not the spec reaches clients as a value
    their generated enum rejects.
    """
    assert _schema("ApiKeyPermission")["enum"] == list(ApiKeyPermission.values)


def test_the_identity_reads_errors_are_the_shape_the_middleware_sends() -> None:
    """`whoami` authenticates in middleware, which answers with a bare
    `message` and does not reach the project exception handler for its credential failures -- so it must not
    publish the handler's `{type, errors[]}` shape the way the deployment
    operations legitimately do.

    Paired with `test_a_rejection_carries_the_body_the_spec_publishes` in
    `platform_api`, which pins the same claim against the wire.
    """
    spec = _committed()
    reads = [
        (path, operation)
        for path, _, operation in _operations(spec)
        if operation["operationId"] == "whoami"
    ]

    # Guarded like its sibling below: without this the whole check is skipped
    # the day the operation id moves.
    assert reads
    for path, operation in reads:
        # 401 only: the published path cannot 403 (see the note beside the
        # response declaration), so declaring one would be a dead branch.
        assert "403" not in operation["responses"], path
        ref = operation["responses"]["401"]["content"]["application/json"]["schema"][
            "$ref"
        ]
        assert ref.endswith("/PlatformKeyError"), f"401 on {path}: {ref}"
    assert set(_schema("PlatformKeyError")["properties"]) == {"message"}


def test_no_published_example_contradicts_its_own_schema() -> None:
    """The standardized-errors schema class appends an example of the exception
    handler's body to every 4xx/5xx, keyed on the status code alone -- so an
    operation that overrides the schema keeps examples describing the shape it
    replaced, and the artifact contradicts itself in one media-type object.

    Checked structurally rather than by name: any response declaring a body
    other than `ErrorResponse` must carry no handler-shaped example.
    """
    matched: set[tuple[str, str, str, str]] = set()
    for path, method, operation in _operations(_committed()):
        for code, response in operation["responses"].items():
            media = response.get("content", {}).get("application/json", {})
            ref = media.get("schema", {}).get("$ref", "")
            if ref.endswith("/ErrorResponse"):
                continue
            for name, example in media.get("examples", {}).items():
                key = (operation["operationId"], code, name, ref.split("/")[-1])
                if key in _KNOWN_EXAMPLE_DIVERGENCES:
                    matched.add(key)
                    continue
                assert "errors" not in example.get("value", {}), (
                    f"{method} {path} {code}: example {name!r} shows the handler "
                    f"body, but the response declares {ref.split('/')[-1]!r}"
                )

    # Debt that pays itself down: once a divergence is fixed upstream its entry
    # stops matching and fails here, instead of lingering and silently
    # suppressing a future regression at the same coordinate.
    assert matched == _KNOWN_EXAMPLE_DIVERGENCES, (
        "these recorded divergences no longer occur and should be deleted: "
        f"{sorted(_KNOWN_EXAMPLE_DIVERGENCES - matched)}"
    )


def test_the_example_contradiction_check_actually_fires() -> None:
    """Every real candidate is currently in `_KNOWN_EXAMPLE_DIVERGENCES`, so the
    assertion above runs zero times against the committed spec. Without this, a
    defect in the check itself would be undetectable.
    """
    media = {
        "schema": {"$ref": "#/components/schemas/ExecutionResponse"},
        "examples": {"Handler": {"value": {"type": "client_error", "errors": []}}},
    }
    ref = media["schema"]["$ref"]
    offending = [
        name
        for name, example in media["examples"].items()
        if not ref.endswith("/ErrorResponse") and "errors" in example.get("value", {})
    ]
    assert offending == ["Handler"]


def test_the_identity_read_asks_for_no_organisation() -> None:
    """Resolving the organisation from the key is the whole point: a path
    parameter here would mean the caller had to know the answer first.
    """
    reads = [
        (path, operation)
        for path, _, operation in _operations(_committed())
        if operation["operationId"] == "whoami"
    ]

    # Guarded like its sibling at `test_the_one_shot_read_...`: an unguarded
    # loop passes by finding nothing the day the operation is renamed.
    assert reads
    for path, operation in reads:
        assert "{" not in path, path
        assert not operation.get("parameters"), path


@pytest.mark.parametrize(
    "exc",
    [APIException("Unauthorized"), ValidationError("at least one file is required")],
)
def test_the_documented_error_body_is_the_one_the_handler_sends(exc) -> None:
    """The error shape comes from the project-wide exception handler, not from
    any view, so nothing else in the spec moves when that handler changes.
    """
    request = APIRequestFactory().post("/deployment/api/org/api/")
    response = drf_logging_exc_handler(exc=exc, context={"request": request})

    error_response = _schema("ErrorResponse")
    error_detail = _schema("ErrorDetail")

    assert set(response.data) == set(error_response["required"])
    assert response.data["type"] in _schema("ErrorType")["enum"]
    for error in response.data["errors"]:
        assert set(error) == set(error_detail["required"])


def test_the_check_flag_passes_on_the_committed_spec() -> None:
    call_command("generate_docstudio_spec", "--check")


def test_the_check_flag_fails_on_a_drifted_spec(tmp_path) -> None:
    drifted = tmp_path / "drifted.json"
    drifted.write_text("{}\n")

    with pytest.raises(CommandError, match="out of date"):
        call_command("generate_docstudio_spec", "--check", "--out", str(drifted))


def test_writing_the_spec_reproduces_the_committed_file(tmp_path) -> None:
    written = tmp_path / "nested" / "spec.json"

    call_command("generate_docstudio_spec", "--out", str(written))

    assert written.read_text() == DEFAULT_OUT.read_text()
