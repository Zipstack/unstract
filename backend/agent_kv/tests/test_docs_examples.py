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

#: The one block allowed to name the OLD path: §11's upgrade item, whose whole
#: job is to say the path moved. Bounded by its own opening words and the next
#: heading, and the test asserts the block is present -- deleting it does not
#: silently widen what the check below tolerates, it fails.
_UPGRADE_ITEM_OPENS = "**The public path moved"
_UPGRADE_ITEM_ENDS = "\n## 12."

#: Every `/api/v1/<segment>` the doc states, wherever it states it. Keying on
#: the placeholder host instead caught only the six `curl` lines -- 6 of the 31
#: occurrences -- so reverting the endpoint HEADINGS, the §1 table and the
#: documented `status_url` while leaving the `curl`s current passed the check.
#: `status_url` is the one documented value a client persists and replays, and
#: the headings are what this file's intra-document anchors resolve against.
_API_PATH = re.compile(r"/api/v1/[a-z0-9-]+")

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


def test_every_documented_path_is_the_mounted_one():
    """The paths the doc states, not just the payloads its examples carry.

    Nothing else ties the two together. The route is mounted from
    `settings.AGENT_KV_PATH_PREFIX` (`backend/backend/base_urls.py`), so
    renaming the public prefix moves every endpoint at once and leaves this
    doc as the stale half, with no way for a reader to tell. That is not
    hypothetical -- the prefix has moved twice, once in depth and once in
    name -- and a stale path does NOT fail in a way a caller can read: it is
    no longer whitelisted past `CustomAuthMiddleware`, so a request carrying a
    Bearer key is tried as a Platform API key and refused with
    `401 Invalid or inactive API key`. The caller is told their credential is
    bad when their URL is stale, which is why this belongs in a test rather
    than in a troubleshooting note.

    Every `/api/v1/...` path in the doc must be the mounted prefix. The two
    other Agent-KV surfaces are deliberately written in forms this does not
    match: key management as `{PATH_PREFIX}/unstract/...` (templated) and the
    internal API under `/internal/v1/`. If either is ever spelled out
    literally, this test is what says so.

    It cannot speak for the customer-facing docs site, which lives in another
    repo and has to be updated by hand.
    """
    doc = _DOC.read_text()

    # Carve out the upgrade item before scanning. It names both paths on
    # purpose; everywhere else, naming the old one is the defect.
    start = doc.find(_UPGRADE_ITEM_OPENS)
    assert start != -1, (
        f"{_DOC.name} no longer contains the upgrade item that opens "
        f"{_UPGRADE_ITEM_OPENS!r}. That block is the only place allowed to name "
        "the pre-rename path, so either restore it or drop this carve-out -- do "
        "not leave the check tolerating an old path with nothing explaining it."
    )
    end = doc.find(_UPGRADE_ITEM_ENDS, start)
    assert end != -1, f"{_DOC.name}: no heading closes the upgrade item"
    upgrade_item, doc = doc[start:end], doc[:start] + doc[end:]

    # The carve-out has to be about the CURRENT path too, or it is just a place
    # for a stale one to hide.
    assert f"/{settings.AGENT_KV_PATH_PREFIX}" in upgrade_item, (
        "the upgrade item does not mention the mounted prefix "
        f"`/{settings.AGENT_KV_PATH_PREFIX}`, so it is not documenting the move"
    )

    paths = _API_PATH.findall(doc)
    # Non-empty, so a doc that stops stating the path -- or a regex that stops
    # matching it -- fails here rather than passing on nothing.
    assert paths, (
        f"no `/api/v1/...` paths found in {_DOC.name}; this guard matches "
        f"`{_API_PATH.pattern}`, and the doc is expected to state the "
        "endpoint it documents"
    )
    want = f"/{settings.AGENT_KV_PATH_PREFIX}"
    for path in sorted(set(paths)):
        assert path == want, (
            f"{_DOC.name} states `{path}`, but the mounted execution prefix is "
            f"`{want}`. If the prefix really moved, the doc is the stale half; "
            "if it did not, AGENT_KV_PATH_PREFIX is overridden in this "
            "environment and the doc is fine."
        )
