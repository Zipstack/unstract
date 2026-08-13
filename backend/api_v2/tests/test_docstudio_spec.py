"""The committed spec is the contract the published clients are generated from.

A route, serializer or schema-annotation change that is not regenerated ships a
spec describing an API the server no longer serves, so drift fails here rather
than in a client repo.
"""

import json

from django.urls import resolve, reverse
from drf_spectacular.drainage import GENERATOR_STATS

from api_v2.management.commands.generate_docstudio_spec import (
    DEFAULT_OUT,
    REGENERATE,
    render_spec,
)


#: Keys under a path item that are operations. The rest -- `parameters`,
#: `summary`, vendor extensions -- describe the path, not a call.
_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def _committed() -> dict:
    return json.loads(DEFAULT_OUT.read_text())


def _operations(spec: dict) -> list[tuple[str, str, dict]]:
    """Every (path, method, operation) the spec documents.

    The spec grows an endpoint at a time, and a check written against exactly
    one of them fails on the next addition without anything being wrong.
    """
    return [
        (path, method, operation)
        for path, path_item in spec["paths"].items()
        for method, operation in path_item.items()
        if method in _METHODS
    ]


def test_committed_spec_matches_the_code() -> None:
    assert DEFAULT_OUT.exists(), f"{DEFAULT_OUT} is missing"
    assert DEFAULT_OUT.read_text() == render_spec(), (
        f"{DEFAULT_OUT} is out of date. Run `{REGENERATE}` from `backend/` and "
        "commit the result."
    )


def test_generation_reports_no_diagnostics() -> None:
    """A warned-about operation is published with guessed request and response
    shapes, and the drift comparison certifies the guess."""
    render_spec()
    assert not GENERATOR_STATS._error_cache
    assert not GENERATOR_STATS._warn_cache


def test_spec_paths_are_the_urls_the_server_serves() -> None:
    """Resolves the real mount rather than restating it: a spec generated for
    URLs the server does not serve is the failure this file exists to catch."""
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


def test_operations_require_the_deployment_key() -> None:
    """Without this the unset DRF authentication default is published as
    though it were a decision, and no generated client can authenticate."""
    spec = _committed()
    scheme = spec["components"]["securitySchemes"]["deploymentKey"]

    assert (scheme["type"], scheme["scheme"]) == ("http", "bearer")
    for path, method, operation in _operations(spec):
        assert operation["security"] == [{"deploymentKey": []}], f"{method} {path}"


def test_clients_can_branch_on_every_failure_they_will_see() -> None:
    for path, method, operation in _operations(_committed()):
        assert {"400", "401", "403", "404", "429", "500"} <= set(
            operation["responses"]
        ), f"{method} {path}"


def test_the_one_shot_read_is_documented_where_a_client_will_see_it() -> None:
    """The semantics that a status read destroys the result must reach the
    generated client, not live in a source comment."""
    reads = [
        operation
        for _, _, operation in _operations(_committed())
        if operation["operationId"] == "status"
    ]

    assert reads
    for status_op in reads:
        assert "one-shot" in status_op["description"]
        assert status_op["responses"]["406"]["description"].strip()
