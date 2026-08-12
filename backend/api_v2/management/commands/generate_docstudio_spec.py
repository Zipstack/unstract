"""Regenerate the committed API deployment OpenAPI spec.

The spec is the contract the published clients and their generated SDKs are
built from, so it is committed and CI fails on drift: change a route, a
serializer or the schema annotation, and regenerate in the same PR.

    python manage.py generate_docstudio_spec
    python manage.py generate_docstudio_spec --check   # CI: no write, drift is an error
"""

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from drf_spectacular.generators import SchemaGenerator

DEFAULT_OUT = Path(__file__).resolve().parents[4] / "specs" / "docstudio-oss.json"
URLCONF = "api_v2.deployment_spec_urls"


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
        schema = SchemaGenerator(urlconf=URLCONF).get_schema(request=None, public=True)
        # Sorted keys are what make the committed artifact a usable drift signal.
        rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"

        out: Path = options["out"]
        if options["check"]:
            current = out.read_text() if out.exists() else ""
            if current != rendered:
                raise CommandError(
                    f"{out} is out of date. Run `python manage.py "
                    f"generate_docstudio_spec` and commit the result."
                )
            self.stdout.write(f"{out} is up to date")
            return

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
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
