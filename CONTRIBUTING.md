# Contributing

See [docs.unstract.com](https://docs.unstract.com/unstract/contributing/unstract).

## PR titles, labels and release branches

Every change merges to `main` first. Release lines are `release/X.Y` branches, and
the Backport workflow copies fixes from `main` to the lines that need them. The PR
labels decide what it copies, so set them when you open the PR.

- **Title:** `TICKET [TYPE] text`, or `[TYPE] text` with no ticket. The `lint-pr`
  check fails on any other form, whatever the labels. The type feeds the changelog; it
  does not decide what Backport copies.
- **A PR into `main` needs exactly one backport label.** `lint-pr` fails without one:
  - **`fix/needs-backport`:** Backport copies it to the release lines still awaiting
    their first release.
  - **`main-only`:** it stays on `main`. Never with a `fix/` label.
  - **`fix/security` or `fix/critical`** (never both): the fix must also reach
    released lines, once the release manager confirms. Either one is enough on its own.
  - **A revert** takes the backport label of the PR it reverts. GitHub's Revert
    button opens it with no label.
  - **Choose by whether a release line needs the change, never from the title type:**
    a `[FIX]` can be `main-only`, and a `[MISC]` can need a backport. If unsure, ask
    whoever raised the PR. Never add a backport label by automation.
- **A PR into `release/X.Y`** needs no backport label, and `lint-pr` refuses `main-only`
  there.
