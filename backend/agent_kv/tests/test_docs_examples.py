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
#: job is to say the path moved. It is bounded by its own opening words and by
#: the start of the NEXT checklist item or section, whichever comes first --
#: not by the next heading. Ending it at the heading exempted the whole tail of
#: §11, and §11 is a checklist that grows per release, so an item appended
#: after this one would have landed inside the exemption. The block's presence
#: is asserted too: deleting it fails rather than silently widening the check.
_UPGRADE_ITEM_OPENS = "**The public path moved"
_UPGRADE_ITEM_CLOSES = re.compile(r"^(\d+\. |## )", re.M)

#: Three patterns, because no one of them subsumes the others. A rename can go
#: wrong in two independent directions -- the NAME of the last segment, and the
#: DEPTH the prefix sits at -- and this doc states the path in three shapes.
#:
#: `_API_PATH` catches the name, in both the `/api/v1/...` and the bare
#: `api/v1/...` shape; the bare one is how §1's prose and §12's
#: environment-reference row state the value an operator copies into `.env`, and
#: a slash-only pattern left both unguarded.
#:
#: `_EXAMPLE_URL` catches the depth. A `curl` written against the placeholder
#: host as `https://api.unstract.example/agentic-extract/` matches no
#: `/api/v1/...` pattern AT ALL, so a path that lost its prefix is invisible to
#: `_API_PATH` -- and that is not hypothetical: the same mistake was live in
#: `docs/agent-kv-architecture.md` earlier in this branch. An earlier revision
#: of this file replaced the host-anchored check with the path one; the two
#: catch different defects and both are needed.
#:
#: `_ANCHOR` catches the links, which carry the path slugified and so contain no
#: slashes at all. Guarding the headings does not guard the links.
_API_PATH = re.compile(r"/?api/v1/[a-z0-9-]+")
_EXAMPLE_URL = re.compile(r"https://api\.unstract\.example(\S*)")
_ANCHOR = re.compile(r"\]\(#([a-z0-9_-]+)\)")

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

    Three shapes are checked, because a rename can go wrong in two
    independent directions and no one pattern sees both: the path's NAME
    (`_API_PATH`, slashed or bare), its DEPTH (`_EXAMPLE_URL`, since a path
    that lost `/api/v1` matches no `/api/v1/...` pattern at all), and the
    intra-document links (`_ANCHOR`, which carry the path slugified).

    Key management is out of scope by construction, not by omission: the doc
    writes it templated as `{PATH_PREFIX}/unstract/...`, so spelling it out
    literally would yield `/api/v1/unstract` and fail the name check. The
    internal API is out of reach rather than out of scope -- it lives under
    `/internal/v1/`, which none of these patterns matches, and the doc already
    spells it out three times.

    It cannot speak for the customer-facing docs site, which lives in another
    repo and has to be updated by hand.
    """
    doc = _DOC.read_text()
    want = f"/{settings.AGENT_KV_PATH_PREFIX}"
    overridden = (
        " (or `AGENT_KV_PATH_PREFIX` is overridden in this environment, in which "
        "case the doc is fine and this is not a doc problem)"
    )

    # Carve out the upgrade item before scanning. It names both paths on
    # purpose; everywhere else, naming the old one is the defect.
    start = doc.find(_UPGRADE_ITEM_OPENS)
    assert start != -1, (
        f"{_DOC.name} no longer contains the upgrade item that opens "
        f"{_UPGRADE_ITEM_OPENS!r}. That block is the only place allowed to name "
        "the pre-rename path, so either restore it or drop this carve-out -- do "
        "not leave the check tolerating an old path with nothing explaining it."
    )
    # End at the next checklist item or section, NOT at the next heading: this
    # item is currently last in its section, so a heading bound would exempt
    # anything appended after it.
    close = _UPGRADE_ITEM_CLOSES.search(doc, start + len(_UPGRADE_ITEM_OPENS))
    assert close, f"{_DOC.name}: nothing closes the upgrade item"
    upgrade_item, doc = doc[start : close.start()], doc[:start] + doc[close.start() :]

    # The carve-out has to be about the CURRENT path too, or it is just a place
    # for a stale one to hide.
    assert want in upgrade_item, (
        f"the upgrade item does not mention the mounted prefix `{want}`, so it "
        f"is not documenting the move{overridden}"
    )

    # 1. The name, in both shapes the doc uses.
    paths = _API_PATH.findall(doc)
    assert paths, (
        f"no `api/v1/...` paths found in {_DOC.name}; this guard matches "
        f"`{_API_PATH.pattern}`, and the doc is expected to state the endpoint "
        "it documents"
    )
    for path in sorted(set(paths)):
        assert path.lstrip("/") == want.lstrip("/"), (
            f"{_DOC.name} states `{path}`, but the mounted execution prefix is "
            f"`{want}`. If the prefix really moved, the doc is the stale "
            f"half{overridden}"
        )

    # 2. The depth. A `curl` that lost `/api/v1` is invisible to the above.
    urls = _EXAMPLE_URL.findall(doc)
    assert urls, (
        f"no example URLs found in {_DOC.name}; this guard matches `curl`s "
        "written against the `https://api.unstract.example` placeholder host"
    )
    for url in sorted(set(urls)):
        assert url == want or url.startswith(f"{want}/"), (
            f"{_DOC.name} documents the URL `{url}`, which is not under the "
            f"mounted prefix `{want}` -- a path at the wrong DEPTH is answered "
            f"by the SPA, not by this API{overridden}"
        )

    # 3. The links, which carry the path slugified and so contain no slashes.
    headings = {
        re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", h.lstrip("# ").strip().lower()))
        for h in _DOC.read_text().splitlines()
        if h.startswith("#")
    }
    unresolved = sorted(set(_ANCHOR.findall(_DOC.read_text())) - headings)
    assert not unresolved, (
        f"{_DOC.name} links to anchors that resolve to no heading: "
        f"{unresolved}. Renaming the prefix renames the endpoint headings, and "
        "the links have to move with them."
    )
