"""FileStorage.rm_exact: delete by exact path, never as a glob.

``FileStorage.rm`` hands its path to fsspec, which expands it as a glob on
every backend that takes the generic delete path (gcsfs, s3fs, adlfs). A
path containing ``[``, ``]``, ``*`` or ``?`` — derived from an uploaded
document's name — is then read as a pattern and the delete fails on GCS/S3
while working on LOCAL. ``rm_exact`` must remove such paths on both.
"""

import uuid
from pathlib import Path

import pytest
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

from tests.llmw_image_fixtures import ObjectStoreLikeMemoryFS

GLOB_NAMES = [
    "Report [CDIC] Final",
    "Invoice *copy*",
    "Scan ? 2",
    "plain name",
]


def _object_store_like() -> FileStorage:
    storage = FileStorage(provider=FileStorageProvider.LOCAL)
    storage.fs = ObjectStoreLikeMemoryFS()
    return storage


@pytest.mark.parametrize("name", GLOB_NAMES)
def test_removes_tree_on_object_store_semantics(name: str) -> None:
    storage = _object_store_like()
    root = f"/{uuid.uuid4().hex}/{name}"
    for rel in ("pages/page_001.png", "pages/page_002.png", "meta.json"):
        storage.fs.pipe(f"{root}/{rel}", b"x")

    storage.rm_exact(root)

    assert storage.fs.find(root) == []


@pytest.mark.parametrize("name", GLOB_NAMES)
def test_removes_nested_tree_on_local(name: str, tmp_path: Path) -> None:
    storage = FileStorage(provider=FileStorageProvider.LOCAL)
    root = tmp_path / name
    (root / "pages" / "sub").mkdir(parents=True)
    for rel in ("pages/page_001.png", "pages/sub/page_002.png", "meta.json"):
        (root / rel).write_bytes(b"x")

    storage.rm_exact(str(root))

    # Files and every directory, deepest first, including the root.
    assert not root.exists()


def test_removes_a_single_file(tmp_path: Path) -> None:
    storage = FileStorage(provider=FileStorageProvider.LOCAL)
    target = tmp_path / "Report [CDIC].png"
    target.write_bytes(b"x")
    sibling = tmp_path / "Report C.png"  # what "[CDIC]" would match as a glob
    sibling.write_bytes(b"y")

    storage.rm_exact(str(target))

    assert not target.exists()
    assert sibling.exists()  # literal match only — never the glob's matches


def test_glob_rm_is_the_failure_this_replaces() -> None:
    # Pins the premise: on object-store semantics plain rm() fails for these
    # names. If fsspec ever stops globbing, this flags that rm_exact may no
    # longer be needed — rather than silently testing nothing.
    storage = _object_store_like()
    root = f"/{uuid.uuid4().hex}/Report [CDIC] Final"
    storage.fs.pipe(f"{root}/page_001.png", b"x")
    with pytest.raises(FileNotFoundError):
        storage.rm(root, recursive=True)
