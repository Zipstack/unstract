"""The committed spec is the contract the published clients are generated from.

A route, serializer or schema-annotation change that is not regenerated ships a
spec describing an API the server no longer serves, so drift fails here rather
than in a client repo.
"""

import json
from pathlib import Path

from drf_spectacular.generators import SchemaGenerator

from api_v2.management.commands.generate_docstudio_spec import DEFAULT_OUT, URLCONF


def _render() -> str:
    schema = SchemaGenerator(urlconf=URLCONF).get_schema(request=None, public=True)
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def test_committed_spec_matches_the_code() -> None:
    assert DEFAULT_OUT.exists(), f"{DEFAULT_OUT} is missing"
    assert DEFAULT_OUT.read_text() == _render(), (
        f"{DEFAULT_OUT} is out of date. Run "
        "`python manage.py generate_docstudio_spec` and commit the result."
    )


def test_spec_covers_the_deployment_routes() -> None:
    """Guards the mount: generating against the included sub-urlconf silently
    drops the prefix, leaving paths the server does not serve."""
    spec = json.loads(Path(DEFAULT_OUT).read_text())
    execute = "/deployment/api/{org_name}/{api_name}/"

    assert set(spec["paths"]) == {execute, f"{execute}mcp/"}
    assert spec["paths"][execute]["post"]["operationId"] == "execute"
    assert spec["paths"][execute]["get"]["operationId"] == "status"
    assert [tag["name"] for tag in spec["tags"]] == ["deployment"]
