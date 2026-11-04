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

from django.core.files.uploadedfile import SimpleUploadedFile

from django.test import override_settings

from agent_kv.execution_serializers import SubmitSerializer

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

#: `backend/agent_kv/tests/` -> repo root.
_DOC = pathlib.Path(__file__).resolve().parents[3] / "docs" / "agent-kv-api.md"

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
