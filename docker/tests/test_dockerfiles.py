"""Tests for Dockerfile structural correctness.

Verifies that the base stage of each service Dockerfile:
- Does NOT declare an ARG VERSION build argument
- Does NOT include a version label derived from ARG VERSION
- DOES include the correct maintainer and description labels
"""

import re
from pathlib import Path

import pytest

# Path to the dockerfiles directory relative to this test file
DOCKERFILES_DIR = Path(__file__).parent.parent / "dockerfiles"

# All Dockerfiles modified in the PR that removes ARG VERSION / version label
ALL_DOCKERFILES = [
    "backend.Dockerfile",
    "platform.Dockerfile",
    "prompt.Dockerfile",
    "runner.Dockerfile",
    "tool-sidecar.Dockerfile",
    "worker-unified.Dockerfile",
    "x2text.Dockerfile",
]

# Expected description label per Dockerfile
EXPECTED_DESCRIPTIONS = {
    "backend.Dockerfile": "Backend Service Container",
    "platform.Dockerfile": "Platform Service Container",
    "prompt.Dockerfile": "Prompt Service Container",
    "runner.Dockerfile": "Runner Service Container",
    "tool-sidecar.Dockerfile": "Tool Sidecar Container",
    "worker-unified.Dockerfile": "Unified Worker Container for All Worker Types",
    "x2text.Dockerfile": "X2Text Service Container",
}

# Expected base image per Dockerfile
EXPECTED_BASE_IMAGES = {
    "backend.Dockerfile": "python:3.12-slim-trixie",
    "platform.Dockerfile": "python:3.12-slim-trixie",
    "prompt.Dockerfile": "python:3.12-slim-trixie",
    "runner.Dockerfile": "python:3.12-slim-trixie",
    "tool-sidecar.Dockerfile": "python:3.12-slim-trixie",
    "worker-unified.Dockerfile": "python:3.12.9-slim",
    "x2text.Dockerfile": "python:3.12-slim-trixie",
}


def read_dockerfile(name: str) -> str:
    """Read and return the content of a Dockerfile."""
    path = DOCKERFILES_DIR / name
    return path.read_text()


def get_base_stage_content(content: str) -> str:
    """Extract the content of the base stage (before the next FROM).

    Returns the lines from the first FROM through the next FROM (exclusive).
    """
    lines = content.splitlines()
    base_lines = []
    in_base = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^FROM\s+\S+\s+AS\s+base\b", stripped, re.IGNORECASE):
            in_base = True
            base_lines.append(line)
        elif in_base:
            # Stop at the next FROM instruction (next stage)
            if re.match(r"^FROM\s+", stripped, re.IGNORECASE):
                break
            base_lines.append(line)
    return "\n".join(base_lines)


def get_label_block_keys(base_stage_content: str) -> list:
    """Extract all label key names from the LABEL instruction in the base stage.

    Handles multi-line LABEL instructions (backslash continuation).
    Returns a list of label key names (e.g., ['maintainer', 'description']).
    """
    lines = base_stage_content.splitlines()
    label_lines = []
    in_label = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^LABEL\b", stripped, re.IGNORECASE):
            in_label = True
            label_lines.append(stripped)
        elif in_label:
            label_lines.append(stripped)
            # Continuation ends when the previous line does NOT end with backslash
            if not label_lines[-2].endswith("\\"):
                break
        if in_label and label_lines and not label_lines[-1].endswith("\\"):
            if len(label_lines) >= 1 and not re.match(r"^LABEL\b", label_lines[-1], re.IGNORECASE):
                break

    label_content = " ".join(label_lines)
    # Find all key=value label pairs
    keys = re.findall(r"\b(\w+)\s*=\s*\"[^\"]*\"", label_content)
    return keys


# ---------------------------------------------------------------------------
# Tests: VERSION ARG removed from base stage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_no_arg_version_in_dockerfile(dockerfile_name: str) -> None:
    """Verify that ARG VERSION is not present anywhere in the Dockerfile."""
    content = read_dockerfile(dockerfile_name)
    # Match any ARG instruction that declares VERSION (with or without default)
    assert not re.search(
        r"^\s*ARG\s+VERSION\b", content, re.MULTILINE
    ), f"{dockerfile_name}: ARG VERSION declaration must not be present (removed in PR)"


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_no_version_label_in_base_stage(dockerfile_name: str) -> None:
    """Verify that the version label is not present in the base stage LABEL instruction."""
    content = read_dockerfile(dockerfile_name)
    base_stage = get_base_stage_content(content)
    # Match 'version=' as a label key (with optional whitespace / backslash continuation)
    assert not re.search(
        r"\bversion\s*=", base_stage, re.IGNORECASE
    ), (
        f"{dockerfile_name}: 'version=' label must not be present in base stage "
        "(removed in PR)"
    )


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_no_version_arg_default_dev(dockerfile_name: str) -> None:
    """Regression: the exact old pattern 'ARG VERSION=dev' must be absent."""
    content = read_dockerfile(dockerfile_name)
    assert "ARG VERSION=dev" not in content, (
        f"{dockerfile_name}: The exact old pattern 'ARG VERSION=dev' "
        "must have been removed by this PR"
    )


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_no_version_label_value_interpolation(dockerfile_name: str) -> None:
    """Regression: the exact old label value 'version=\"${VERSION}\"' must be absent."""
    content = read_dockerfile(dockerfile_name)
    assert 'version="${VERSION}"' not in content, (
        f"{dockerfile_name}: The old label 'version=\"${{VERSION}}\"' "
        "must have been removed by this PR"
    )


# ---------------------------------------------------------------------------
# Tests: Required labels ARE present in base stage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_maintainer_label_present(dockerfile_name: str) -> None:
    """Verify that the maintainer label with the correct value is present."""
    content = read_dockerfile(dockerfile_name)
    base_stage = get_base_stage_content(content)
    assert re.search(
        r'maintainer\s*=\s*"Zipstack Inc\."', base_stage, re.IGNORECASE
    ), f"{dockerfile_name}: LABEL maintainer=\"Zipstack Inc.\" must be present in base stage"


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_description_label_present(dockerfile_name: str) -> None:
    """Verify that the description label with the correct service-specific value is present."""
    content = read_dockerfile(dockerfile_name)
    base_stage = get_base_stage_content(content)
    expected = EXPECTED_DESCRIPTIONS[dockerfile_name]
    assert re.search(
        rf'description\s*=\s*"{re.escape(expected)}"', base_stage
    ), (
        f"{dockerfile_name}: LABEL description=\"{expected}\" "
        "must be present in base stage"
    )


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_label_has_exactly_two_keys(dockerfile_name: str) -> None:
    """Verify the base stage LABEL contains exactly 'maintainer' and 'description'.

    After removing 'version', the LABEL instruction must contain only
    maintainer and description (no other label keys remain).
    """
    content = read_dockerfile(dockerfile_name)
    base_stage = get_base_stage_content(content)
    label_keys = get_label_block_keys(base_stage)
    assert set(label_keys) == {
        "maintainer",
        "description",
    }, (
        f"{dockerfile_name}: base stage LABEL must contain only 'maintainer' and "
        f"'description' keys, got: {label_keys}"
    )


# ---------------------------------------------------------------------------
# Tests: Base stage FROM instruction is correct
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_base_stage_from_instruction(dockerfile_name: str) -> None:
    """Verify that the base stage FROM instruction uses the expected Python image."""
    content = read_dockerfile(dockerfile_name)
    expected_image = EXPECTED_BASE_IMAGES[dockerfile_name]
    # Match the first FROM ... AS base
    match = re.search(
        r"^FROM\s+(\S+)\s+AS\s+base\b", content, re.MULTILINE | re.IGNORECASE
    )
    assert match is not None, f"{dockerfile_name}: No 'FROM ... AS base' instruction found"
    actual_image = match.group(1)
    assert actual_image == expected_image, (
        f"{dockerfile_name}: Expected base image '{expected_image}', "
        f"got '{actual_image}'"
    )


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_dockerfile_file_exists(dockerfile_name: str) -> None:
    """Verify that each Dockerfile actually exists at the expected path."""
    path = DOCKERFILES_DIR / dockerfile_name
    assert path.exists(), f"Dockerfile not found: {path}"
    assert path.is_file(), f"Expected a file, not a directory: {path}"


# ---------------------------------------------------------------------------
# Tests: Boundary / negative cases
# ---------------------------------------------------------------------------


def test_version_arg_removed_not_merely_commented(dockerfile_name: str = "backend.Dockerfile") -> None:
    """Regression: the VERSION ARG is not present even as a comment."""
    content = read_dockerfile(dockerfile_name)
    # The arg must not appear as an active instruction anywhere
    active_lines = [
        line for line in content.splitlines() if not line.strip().startswith("#")
    ]
    active_content = "\n".join(active_lines)
    assert not re.search(r"^\s*ARG\s+VERSION\b", active_content, re.MULTILINE), (
        "backend.Dockerfile: ARG VERSION must not appear as an active (non-comment) "
        "instruction"
    )


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_no_version_key_in_any_stage(dockerfile_name: str) -> None:
    """Verify that no stage in the Dockerfile contains a 'version=' label key.

    This ensures the version label was not inadvertently moved to another stage.
    """
    content = read_dockerfile(dockerfile_name)
    # Exclude comment lines when searching for label keys
    active_lines = [
        line for line in content.splitlines() if not line.strip().startswith("#")
    ]
    active_content = "\n".join(active_lines)
    assert not re.search(r"\bversion\s*=\s*\"", active_content, re.IGNORECASE), (
        f"{dockerfile_name}: 'version=' label must not appear in any stage of the "
        "Dockerfile (not just base stage)"
    )


@pytest.mark.parametrize("dockerfile_name", ALL_DOCKERFILES)
def test_worker_unified_distinct_base_image(dockerfile_name: str) -> None:
    """Verify worker-unified uses python:3.12.9-slim while others use python:3.12-slim-trixie."""
    content = read_dockerfile(dockerfile_name)
    match = re.search(
        r"^FROM\s+(\S+)\s+AS\s+base\b", content, re.MULTILINE | re.IGNORECASE
    )
    assert match is not None
    actual_image = match.group(1)
    if dockerfile_name == "worker-unified.Dockerfile":
        assert actual_image == "python:3.12.9-slim", (
            "worker-unified.Dockerfile must use python:3.12.9-slim as base image"
        )
    else:
        assert actual_image == "python:3.12-slim-trixie", (
            f"{dockerfile_name}: non-worker-unified Dockerfiles must use "
            "python:3.12-slim-trixie as base image"
        )