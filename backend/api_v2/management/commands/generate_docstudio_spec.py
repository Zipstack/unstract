"""Regenerate the committed API deployment OpenAPI spec.

The spec is the contract the published clients and their generated SDKs are
built from, so it is committed and CI fails on drift: change a route, a
serializer or the schema annotation, and regenerate in the same PR.

    uv run python manage.py generate_docstudio_spec           # from backend/
    uv run python manage.py generate_docstudio_spec --check   # no write, drift is an error

The generated paths carry ``API_DEPLOYMENT_PATH_PREFIX`` or ``PATH_PREFIX``
depending on the mount, so generation refuses to produce a spec mounted anywhere
but the public defaults: the committed artifact describes the API as it is
served publicly, not as one installation chooses to mount it.
"""

import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema

DEFAULT_OUT = Path(__file__).resolve().parents[4] / "specs" / "docstudio-oss.json"
URLCONF = "api_v2.deployment_spec_urls"
REGENERATE = "uv run python manage.py generate_docstudio_spec"
# The mounts these routes are served at publicly. `API_DEPLOYMENT_PATH_PREFIX`
# and `PATH_PREFIX` can move them per installation, and a spec carrying a
# private prefix would send every generated client to a URL only that
# installation answers. Written as literals rather than read from settings, so
# an override fails the gate rather than being baked into the artifact.
#
# Each entry is the *route*, not the mount it hangs off. `api/v1/unstract` alone
# is exactly `TENANT_SUBFOLDER_PREFIX`, so with a `startswith` over the union an
# `API_DEPLOYMENT_PATH_PREFIX` pointed anywhere under the tenant mount --
# `api/v1/unstract/deploy`, say -- passed the gate this comment says it fails.
PUBLISHED_PATH_PREFIXES = ("deployment", "api/v1/unstract/whoami")
# Named in every failure message: the repos that regenerate from this file are
# the ones a spec change actually breaks, and nothing there watches this repo.
DOWNSTREAM = (
    "The published client (Zipstack/unstract-python-client) and the CLI "
    "(Zipstack/unstract-cli) are generated from this file — raise the matching "
    "PRs there for anything that changes an operation id, a tag or a schema."
)

# A literal for the same reason as `PUBLISHED_PATH_PREFIXES`.
TENANT_MOUNT = "/api/v1/unstract/"
ORG_SEGMENT = "{org_id}"
HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)
ORG_SEGMENT_PARAMETER = {
    "in": "path",
    "name": "org_id",
    "required": True,
    "schema": {"type": "string"},
    "description": (
        "The organisation the request is scoped to, as `whoami` reports it in "
        "`organization_id`."
    ),
}


def _restore_organisation_segment(schema: dict[str, Any]) -> None:
    """Put back the organisation segment the router never sees.

    `OrganizationMiddleware` strips it before routing, so paths taken from the
    URLconf are not the ones callers send. The routes genuinely served without
    it are the ones that setting whitelists, so it decides this too.
    """
    for url in [url for url in schema["paths"] if url.startswith(TENANT_MOUNT)]:
        if any(
            re.match(whitelisted, url)
            for whitelisted in settings.ORGANIZATION_MIDDLEWARE_WHITELISTED_PATHS
        ):
            continue
        item = schema["paths"].pop(url)
        for method, operation in item.items():
            if method in HTTP_METHODS:
                operation.setdefault("parameters", []).append(dict(ORG_SEGMENT_PARAMETER))
        schema["paths"][f"{TENANT_MOUNT}{ORG_SEGMENT}/{url[len(TENANT_MOUNT):]}"] = item


class SpecGenerationFailed(CommandError):
    """Raised when the generator had to guess."""


def render_spec() -> str:
    """The committed artifact, byte for byte.

    Shared with the drift test: two copies of this could disagree, and then
    the gate rejects exactly the file the command it names produces.
    """
    GENERATOR_STATS.reset()
    schema = SchemaGenerator(urlconf=URLCONF).get_schema(request=None, public=True)
    if GENERATOR_STATS:
        # An operation spectacular could not resolve is published with no
        # request body and an empty response rather than dropped, which reads
        # downstream as an annotation that is simply thin. Both caches are
        # drained because the severity a given diagnostic carries is
        # spectacular's choice, not something to rely on.
        diagnostics = "\n".join(
            f"  {severity}: {message}"
            for severity, cache in (
                ("error", GENERATOR_STATS._error_cache),
                ("warning", GENERATOR_STATS._warn_cache),
            )
            for message in cache
        )
        raise SpecGenerationFailed(
            f"The generator reported problems, so the spec would describe an "
            f"API nobody implements:\n{diagnostics}"
        )

    _restore_organisation_segment(schema)

    published = tuple(f"/{prefix}/" for prefix in PUBLISHED_PATH_PREFIXES)
    off_prefix = [path for path in schema["paths"] if not path.startswith(published)]
    if off_prefix:
        raise SpecGenerationFailed(
            f"Generated paths are outside the published mounts "
            f"({', '.join(published)}): {', '.join(sorted(off_prefix))}. Unset "
            f"API_DEPLOYMENT_PATH_PREFIX and PATH_PREFIX and regenerate."
        )

    # Hand-written fragments (path parameter schemas, security schemes) reach
    # the output verbatim, so nothing above would notice a typo in one.
    try:
        validate_schema(schema)
    except Exception as error:
        raise SpecGenerationFailed(f"The generated spec is not valid OpenAPI: {error}")

    # Sorted keys are what make the committed artifact a usable drift signal.
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


class Command(BaseCommand):
    help = "Generate the API deployment OpenAPI spec."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
        parser.add_argument(
            "--check",
            action="store_true",
            help="Fail if the file on disk differs, instead of writing it.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        rendered = render_spec()

        out: Path = options["out"]
        if options["check"]:
            current = out.read_text() if out.exists() else ""
            if current != rendered:
                raise CommandError(
                    f"{out} is out of date. Run `{REGENERATE}` from `backend/` "
                    f"and commit the result.\n\n{DOWNSTREAM}"
                )
            self.stdout.write(f"{out} is up to date")
            return

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
        schema = json.loads(rendered)
        operations = sum(
            1
            for methods in schema["paths"].values()
            for method in methods
            if method in {"get", "post", "put", "patch", "delete"}
        )
        self.stdout.write(
            f"{out}: {len(schema['paths'])} paths, {operations} operations, "
            f"{len(schema.get('components', {}).get('schemas', {}))} schemas"
        )
