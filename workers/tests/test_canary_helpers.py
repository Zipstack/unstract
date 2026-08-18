"""Unit tests for the shared ``iter_production_trees`` helper.

Locks the fail-loud-by-default contract that the canary modules
(``test_executor_dispatch``, ``test_fairness_key``) rely on via
``pytestmark = pytest.mark.filterwarnings("error::UserWarning")``.
Without that promotion an unparseable production file would be
silently dropped and every canary would pass vacuously over a
smaller tree — exactly the failure mode this helper claims to
prevent.
"""

from __future__ import annotations

import warnings

import pytest

from .canary_helpers import iter_production_trees


class TestUnparseableFileBehaviour:
    def test_unparseable_file_emits_userwarning(self, tmp_path, monkeypatch):
        """Drop a syntactically invalid .py inside the audited root
        and confirm the helper surfaces the failure as a
        ``UserWarning`` (the signal the canary modules promote to
        error). Without this, a botched merge in production would
        leave canaries silently green.
        """
        from . import canary_helpers

        # Point the helper at an isolated tree so we don't pollute
        # the real workers/ root with a broken file.
        monkeypatch.setattr(canary_helpers, "WORKERS_ROOT", tmp_path)
        (tmp_path / "broken.py").write_text("def oops(:\n")
        (tmp_path / "ok.py").write_text("x = 1\n")

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", UserWarning)
            result = iter_production_trees(skip_top_dirs=frozenset())

        # The good file still made it into the audit set.
        assert any(rel.name == "ok.py" for rel, _ in result)
        # The broken one is skipped *and* warned about.
        assert not any(rel.name == "broken.py" for rel, _ in result)
        assert any(
            "unparseable" in str(w.message) and "broken.py" in str(w.message)
            for w in captured
            if issubclass(w.category, UserWarning)
        )

    def test_warning_promoted_to_error_under_filterwarnings(
        self, tmp_path, monkeypatch
    ):
        """When the caller installs
        ``pytest.mark.filterwarnings("error::UserWarning")`` (or the
        equivalent ``warnings.simplefilter("error", UserWarning)``)
        the helper fails loud instead of silently skipping. This is
        the contract the canary modules at module level rely on.
        """
        from . import canary_helpers

        monkeypatch.setattr(canary_helpers, "WORKERS_ROOT", tmp_path)
        (tmp_path / "broken.py").write_text("def oops(:\n")

        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            with pytest.raises(UserWarning, match="unparseable"):
                iter_production_trees(skip_top_dirs=frozenset())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
