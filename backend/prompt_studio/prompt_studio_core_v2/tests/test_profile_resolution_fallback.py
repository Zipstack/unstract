"""Regression tests for profile resolution in ``fetch_response``.

Pins the fix for the CLI-surfaced bug where a prompt with no
``profile_manager`` FK raised ``DefaultProfileError`` even though the project
had a default LLM profile configured. ``index_document`` and single-pass
extraction already fell back to ``ProfileManager.get_default_llm_profile``;
``fetch_response`` was the lone omission.

The resolution ladder these tests lock down, in order:

  1. An explicitly passed ``profile_manager_id`` wins over everything.
  2. Otherwise the prompt's own ``profile_manager`` FK.
  3. Otherwise the project default (``get_default_llm_profile``) -- the rung
     this PR added, and the one the CLI hit.
  4. If none resolves, ``DefaultProfileError`` propagates.

Deleting either inserted fallback must turn rung 3 red. The suite was fully
green with both removed before these tests existed.

Both call sites -- ``build_fetch_response_payload`` (async dispatch) and
``_fetch_response`` (synchronous) -- carry the same five lines, so both are
exercised: a fix applied to only one of them is a real regression.

Rather than driving the whole function (which needs storage, indexing and an
LLM round-trip), the ladder is extracted from the real source and executed
against stubs. The extraction is anchored on the exact lines the fix added, so
if the fallback is deleted or reworded the test fails loudly instead of quietly
passing against a stale copy.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

HELPER = Path(__file__).resolve().parents[1] / "prompt_studio_helper.py"

# The exact block the fix inserted, at both call sites.
FALLBACK_SNIPPET = (
    "if not profile_manager:\n"
    "            profile_manager = ProfileManager.get_default_llm_profile(tool)"
)

CALL_SITES = {
    "build_fetch_response_payload": "        profile_manager = prompt.profile_manager\n",
    "_fetch_response": "        profile_manager = prompt.profile_manager\n",
}


class _Sentinel:
    """Stands in for a ProfileManager; identity is all the ladder cares about."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.label}>"


class DefaultProfileError(Exception):
    pass


EXPLICIT = _Sentinel("explicit-profile")
PROMPT_FK = _Sentinel("prompt-fk-profile")
PROJECT_DEFAULT = _Sentinel("project-default-profile")


def _extract_ladders() -> list[str]:
    """Return the resolution ladder source from every call site that has one.

    Fails if a call site is missing the fallback, which is exactly the
    regression this module exists to catch.
    """
    source = HELPER.read_text()
    occurrences = source.count(FALLBACK_SNIPPET)
    if occurrences < len(CALL_SITES):
        pytest.fail(
            f"Expected the project-default fallback at {len(CALL_SITES)} call "
            f"sites in {HELPER.name}, found {occurrences}. If the fallback was "
            "removed or reworded, restore it or update this test - do not "
            "delete the test."
        )

    anchor_text = "        profile_manager = prompt.profile_manager\n"
    ladders = []
    anchor = source.find(anchor_text)
    while anchor != -1:
        end = source.index(FALLBACK_SNIPPET, anchor) + len(FALLBACK_SNIPPET)
        ladders.append(textwrap.dedent(source[anchor:end]))
        anchor = source.find(anchor_text, end)
    return ladders


def _run_ladder(
    ladder_src: str,
    *,
    profile_manager_id: str | None,
    prompt_fk: Any,
    default_profile: Any,
) -> Any:
    """Execute one extracted ladder against stubbed collaborators."""

    class _ProfileManagerHelper:
        @staticmethod
        def get_profile_manager(profile_manager_id: str) -> Any:
            return EXPLICIT

    class _ProfileManager:
        @staticmethod
        def get_default_llm_profile(tool: Any) -> Any:
            if default_profile is None:
                raise DefaultProfileError("Default ProfileManager does not exist.")
            return default_profile

    namespace: dict[str, Any] = {
        "prompt": type("Prompt", (), {"profile_manager": prompt_fk})(),
        "profile_manager_id": profile_manager_id,
        "tool": object(),
        "ProfileManagerHelper": _ProfileManagerHelper,
        "ProfileManager": _ProfileManager,
    }
    exec(compile(ladder_src, str(HELPER), "exec"), namespace)
    return namespace["profile_manager"]


LADDERS = _extract_ladders()


@pytest.mark.parametrize("ladder", LADDERS, ids=list(CALL_SITES))
class TestProfileResolutionLadder:
    """Every rung, at every call site that carries the fallback."""

    def test_prompt_without_profile_uses_project_default(self, ladder: str) -> None:
        """The reported bug: no FK + a project default must resolve, not raise."""
        resolved = _run_ladder(
            ladder,
            profile_manager_id=None,
            prompt_fk=None,
            default_profile=PROJECT_DEFAULT,
        )

        assert resolved is PROJECT_DEFAULT, (
            "A prompt with no profile FK must fall back to the project default; "
            "this is the case that raised DefaultProfileError before the fix"
        )

    def test_prompt_fk_wins_over_project_default(self, ladder: str) -> None:
        """The fallback must not override a profile the prompt already has."""
        resolved = _run_ladder(
            ladder,
            profile_manager_id=None,
            prompt_fk=PROMPT_FK,
            default_profile=PROJECT_DEFAULT,
        )

        assert resolved is PROMPT_FK

    def test_explicit_id_wins_over_everything(self, ladder: str) -> None:
        resolved = _run_ladder(
            ladder,
            profile_manager_id="some-profile-id",
            prompt_fk=PROMPT_FK,
            default_profile=PROJECT_DEFAULT,
        )

        assert resolved is EXPLICIT

    def test_no_profile_anywhere_still_raises(self, ladder: str) -> None:
        """The fallback must not swallow a genuinely unconfigured project."""
        with pytest.raises(DefaultProfileError):
            _run_ladder(
                ladder,
                profile_manager_id=None,
                prompt_fk=None,
                default_profile=None,
            )


def test_fallback_is_present_at_both_call_sites() -> None:
    """Guards against fixing one call site and not the other."""
    assert len(LADDERS) == len(CALL_SITES), (
        f"Expected {len(CALL_SITES)} call sites carrying the project-default "
        f"fallback, found {len(LADDERS)}"
    )
