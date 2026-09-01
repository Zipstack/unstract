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
from workflow_manager.endpoint_v2.dto import FileExecutionResult
from workflow_manager.workflow_v2.dto import ExecutionResponse

from api_v2.management.commands.generate_docstudio_spec import (
    DEFAULT_OUT,
    DOWNSTREAM,
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
_KNOWN_EXAMPLE_DIVERGENCES = {
    ("status", "406"),
    ("status", "500"),
    ("execute", "500"),
}

#: The operations served by an API deployment, as opposed to the platform-key
#: operations that describe the account. They authenticate differently and can
#: fail differently, so several checks below split on this.
DEPLOYMENT_OPERATIONS = {"execute", "status"}


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


def test_spec_paths_are_the_urls_the_server_serves() -> None:
    """Resolves the real mount rather than restating it: a spec generated for
    URLs the server does not serve is the failure this file exists to catch.
    """
    served = reverse(
        "api_deployment_execution", kwargs={"org_name": "ORG", "api_name": "API"}
    )
    documented = [
        path.replace("{org_name}", "ORG").replace("{api_name}", "API")
        for path in _committed()["paths"]
    ]

    assert served.rstrip("/") in [path.rstrip("/") for path in documented]
    for path in documented:
        # Raises Resolver404 if the spec documents a URL nothing answers.
        resolve(path if path.endswith("/") else f"{path}/")


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
    """Every operation authenticates and can fail on the server, so these three
    are the branches a client needs whatever it is calling.
    """
    for path, method, operation in _operations(_committed()):
        assert {"401", "403", "500"} <= set(operation["responses"]), f"{method} {path}"


def test_the_deployment_operations_document_a_rejected_request_and_a_missing_one() -> (
    None
):
    """Kept off the universal check above: a request carrying no body and
    naming no resource cannot be malformed or miss its target, and documenting
    a status an operation cannot return hands clients a dead branch.
    """
    for path, method, operation in _operations(_committed()):
        declared = {"400", "404"} & set(operation["responses"])
        if operation["operationId"] in DEPLOYMENT_OPERATIONS:
            assert declared == {"400", "404"}, f"{method} {path}"
        else:
            assert not declared, f"{method} {path}"


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
    `message` and never reaches the project exception handler -- so it must not
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
    # the day the operation id moves, which is the same vacuity this commit
    # fixed twelve lines down and reintroduced here.
    assert reads
    for path, operation in reads:
        for code in ("401", "403"):
            ref = operation["responses"][code]["content"]["application/json"]["schema"][
                "$ref"
            ]
            assert ref.endswith("/PlatformKeyError"), f"{code} on {path}: {ref}"
    assert set(_schema("PlatformKeyError")["properties"]) == {"message"}


def test_no_published_example_contradicts_its_own_schema() -> None:
    """The standardized-errors schema class appends an example of the exception
    handler's body to every 4xx/5xx, keyed on the status code alone -- so an
    operation that overrides the schema keeps examples describing the shape it
    replaced, and the artifact contradicts itself in one media-type object.

    Checked structurally rather than by name: any response declaring a body
    other than `ErrorResponse` must carry no handler-shaped example.
    """
    for path, method, operation in _operations(_committed()):
        if (operation["operationId"], "") in _KNOWN_EXAMPLE_DIVERGENCES:
            continue
        for code, response in operation["responses"].items():
            media = response.get("content", {}).get("application/json", {})
            ref = media.get("schema", {}).get("$ref", "")
            if ref.endswith("/ErrorResponse"):
                continue
            for name, example in media.get("examples", {}).items():
                if (operation["operationId"], code) in _KNOWN_EXAMPLE_DIVERGENCES:
                    continue
                assert "errors" not in example.get("value", {}), (
                    f"{method} {path} {code}: example {name!r} shows the handler "
                    f"body, but the response declares {ref.split('/')[-1]!r}"
                )


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
