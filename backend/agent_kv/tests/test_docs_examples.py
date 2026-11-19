"""The curl examples in `docs/agent-kv-api.md` must actually validate.

These are the payloads a customer copies. Nothing else checks them: the doc is
prose to every other test in this suite, so an example can drift from the
serializer silently and the first person to find out is an integrator getting a
400 from a documented request.

It happened in the direction this file now guards. The `kv` example carried no
`adapters` block and a note saying the extractor was env-configured on the
operator side -- correct when written, wrong after the adapter migration made
all three roles required. A reader following it got "llm: This field is
required."

Both the doc and this app are in the OSS repo, so this runs in CI rather than
skipping the way the chart cross-checks in `extraction_seams` must.
"""

import json
import os
import pathlib
import re

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from agent_kv.execution_serializers import SubmitSerializer

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

#: `backend/agent_kv/tests/` -> repo root.
_DOC = pathlib.Path(__file__).resolve().parents[3] / "docs" / "agent-kv-api.md"

#: The placeholder host every `curl` in the doc is written against. Capturing
#: the path after it is what lets the prefix check below compare a documented
#: URL with the route the service actually mounts.
_EXAMPLE_URL = re.compile(r"https://api\.unstract\.example(\S*)")

#: The `-F 'extractors=[...]'` argument of each fenced curl example. Matching on
#: the curl flag rather than on a fence keeps prose that merely mentions
#: `extractors` out of it.
_EXTRACTORS_ARG = re.compile(r"-F 'extractors=(\[.*?\])'", re.DOTALL)


def _documented_entries() -> list[dict]:
    assert _DOC.is_file(), (
        f"{_DOC} is missing. Both this app and the doc live in the OSS repo, so "
        "this is a move or a rename, not an environment difference -- repoint "
        "`_DOC` rather than making this test skip."
    )
    blocks = _EXTRACTORS_ARG.findall(_DOC.read_text())
    # Deliberately exact: one example per shipped extractor. A new example that
    # does not parse, or a lost one, both show up here rather than as a silently
    # smaller loop.
    assert len(blocks) == 2, (
        f"expected one curl example per extractor, found {len(blocks)}. If an "
        "example was added, extend this and the coverage assertion below; if "
        "one stopped matching, its `-F 'extractors=...'` argument changed shape"
    )
    entries = []
    for block in blocks:
        parsed = json.loads(block)
        assert isinstance(parsed, list) and len(parsed) == 1
        entries.append(parsed[0])
    return entries


def _pdf_upload(name="doc.pdf"):
    with open(os.path.join(FIXTURES, "two_page.pdf"), "rb") as f:
        return SimpleUploadedFile(name, f.read(), content_type="application/pdf")


@override_settings(AGENT_KV_KV_EXTRACTOR_ENABLED=True)
def test_every_documented_example_validates():
    """Through `SubmitSerializer`, which is the gate a real request passes.

    **Not `ExtractorSerializer`.** That one validates an entry's own fields and
    never looks at `adapters`: `_validated_adapter_shape` is called from
    `SubmitSerializer.validate_extractors`, after the entry serializer has
    already returned. A first version of this test used `ExtractorSerializer`
    and survived its own mutation -- deleting the `adapters` block from the
    documented `kv` example left it green, which is precisely the drift the
    file exists to catch. Validating through the submit serializer costs a
    fixture upload and checks the thing that matters.
    """
    for entry in _documented_entries():
        ser = SubmitSerializer(
            data={"file": _pdf_upload(), "extractors": json.dumps([entry])}
        )
        assert ser.is_valid(), (
            f"the documented `{entry.get('name')}` example is rejected at "
            f"submit: {json.dumps(ser.errors)}"
        )


def test_the_examples_cover_both_extractors():
    """Guards the loop above from passing on two copies of one extractor."""
    assert {e["name"] for e in _documented_entries()} == {"kv", "table"}


def test_the_documented_urls_sit_under_the_live_execution_prefix():
    """The path the examples are written against, not just their payloads.

    Nothing else ties the two together. The route is mounted from
    `settings.AGENT_KV_PATH_PREFIX` (`backend/base_urls.py`), so renaming the
    public prefix moves every endpoint and leaves a doc full of `curl`s that
    now 404 -- and a reader has no way to tell the doc is the stale half. That
    is not hypothetical: the prefix was renamed once, and this assertion is
    what makes the next rename fail here instead of in an integrator's
    terminal.

    It cannot speak for the customer-facing docs site, which lives in another
    repo and has to be updated by hand.
    """
    paths = _EXAMPLE_URL.findall(_DOC.read_text())
    # Non-empty, so a doc that stops using the placeholder host -- or a regex
    # that stops matching it -- fails here rather than passing on nothing.
    assert paths, (
        "no example URLs found in the doc; this guard matches `curl`s written "
        f"against the `{_EXAMPLE_URL.pattern}` placeholder host"
    )
    prefix = f"/{settings.AGENT_KV_PATH_PREFIX}"
    for path in paths:
        assert path == prefix or path.startswith(f"{prefix}/"), (
            f"the doc documents `{path}`, which is not under the mounted "
            f"execution prefix `{prefix}`"
        )
