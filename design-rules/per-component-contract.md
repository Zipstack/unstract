# Per-component contract

Every per-component `DESIGN_RULES.md` file in this repo (one per active Django app under `backend/`, per shared library under `unstract/`, and per worker under `workers/`) follows this contract.

This file holds the rationale and the rules-about-rules that would otherwise be duplicated across every per-component file. The reviewer-facing parts — the Compatibility blockquote and the link to the Definition of Done — are still inlined in every per-component file because PR reviewers and diff-scoped review bots need to see them in the file under review without following links.

The canonical Definition of Done lives in [`definition-of-done.md`](definition-of-done.md), not in this file.

**Worked example:** [`backend/account_v2/DESIGN_RULES.md`](../backend/account_v2/DESIGN_RULES.md) — copy this file's structure when creating a new per-component file.

---

## Section structure (the only allowed shape)

Every per-component `DESIGN_RULES.md` contains, in this order:

| # | Section |
|---|---|
| 1 | Title — `# <component> — Design Rules` |
| 2 | One-line component intro paragraph |
| 3 | Compatibility blockquote (verbatim — see below) |
| 4 | Contract pointer paragraph (one line linking to this file) |
| 5 | `## Scope` — two-row table with `**Covers**` and `**Excludes**` |
| 6 | `## Read first` — table of files and why each binds here |
| 7 | `## Rules` — `R1`..`Rn`, each rendered as an `### R<N> — <title>` heading followed by a 4-row table (Severity / Why / Refs / Enforced by). If the component has no rules yet, the section contains the single line `No component-specific rules yet.` |
| 8 | `## Known Exceptions` (optional) — present *only* when at least one intentional, accepted exception exists. Each entry is a `### <descriptive title>` heading with a 3-row table (Rule / Why / Tracked in). Omit the section entirely when there are none. |
| 9 | `## Checklist` — single line linking to `definition-of-done.md` |

Place a `---` horizontal rule between major content sections (after the Contract pointer, after `Read first`, after `Rules`). They create the visual breaks that make the file scannable in a github diff or markdown preview but are not themselves "sections."

There is no `## What this is`, no `## Examples`, no inline DoD body, no `Status` field anywhere.

|  |  |
|---|---|
| **Target size** | ~70 lines per file. A file longer than 100 lines is a code smell — split the component or move detail into an ADR. (The table layout adds vertical space; substance budget is still small.) |
| **Rule count** | 5–7 rules per component. Hard ceiling 10. If a component needs more, the component is too coarse and should be split. |

---

## The Compatibility blockquote (verbatim)

Every per-component file places this blockquote immediately after the intro paragraph, exactly once, with the bold `**Compatibility:**` label:

```
> **Compatibility:** All changes to this component must remain compatible with extension by an external layer that runs this codebase alongside additional Django applications sharing the same database.
```

`validate.sh` greps for the literal substring `All changes to this component must remain compatible` (the grep tolerates the `**Compatibility:**` markdown bold form as well as a plain `Compatibility:` label, since the substring sits after both). Do not paraphrase the rest of the sentence.

---

## The Contract pointer paragraph (one line)

Immediately under the Compatibility blockquote, on its own paragraph:

```
This file follows the [per-component contract](../../design-rules/per-component-contract.md) (rule format, severity vocabulary, Known Exceptions, M1/M2/M3 meta-rules).
```

The exact relative path depends on the depth of the per-component file — verify it resolves to `design-rules/per-component-contract.md` from the file's directory before merging.

---

## Rule format

Every rule in the `## Rules` section uses this exact format — an `H3` heading followed by a 4-row, 2-column markdown table:

```markdown
### R1 — <one-sentence rule>

|  |  |
|---|---|
| **Severity** | MUST · SHOULD · MAY |
| **Why** | <reason — principle, ADR, or past incident> |
| **Refs** | <principles.md#PN · adr/ADR-NNN · security/...> |
| **Enforced by** | <test path | middleware | CI check | code review only | not yet enforced — <ref>> |
```

Every rule must have all four rows (Severity, Why, Refs, Enforced by). Rule-field presence and checklist-section presence are checked at code review today — `validate.sh` does not yet parse rule tables; it currently only verifies the Compatibility blockquote substring, the forbidden-word list, and component-directory sanity. A future hardening pass may extend it to enforce the full rule format; until then, reviewers are the enforcement.

The middle dot (`·`) is the canonical separator for multiple `Refs` entries — easier to scan than a comma in a table cell.

**Severity** uses RFC 2119 vocabulary. Definitions are in [`definition-of-done.md`](definition-of-done.md#severity-vocabulary-used-by-rules). If a rule has no severity tag, the reviewer treats it as MUST.

**Enforced by** must always be a non-empty value. Legitimate values include:

| Value | Use when |
|---|---|
| A specific test path | e.g. `tests/test_tenant_isolation.py::test_org_filter_backend` |
| A middleware or class name | e.g. `CustomAuthMiddleware` |
| A CI check | e.g. `ci: pre-commit hook ruff S608` |
| `code review only` | For rules that have no automated check today but are routinely caught at PR review |
| `not yet enforced — <tracker reference>` | For rules that describe current expected behaviour but have no enforcement at all yet; the tracker reference is required so the gap is visible |

A rule with `Enforced by: not yet enforced` is still a real rule, but it is honest about being unverified.

---

## Rule numbering convention

- Rule IDs are stable: `R1`, `R2`, … assigned in creation order.
- A rule ID is **never reused**. Removing a rule leaves a gap. The next new rule takes the next free number after the highest ever used in this file.
- Rules are scoped to the file they live in. Inside a per-component file, refer to a rule as `R<N>` (e.g. "R2 covers this case").
- Cite a rule from outside its file as `<component>.R<N>` — for example `account_v2.R2` or `connector_v2.R5`. Use the path-style component name (`unstract/sdk1.R1`) when two components share a base name across `backend/`, `unstract/`, and `workers/`.

---

## Known Exceptions format

`## Known Exceptions` records intentional deviations from a rule that have been accepted as legitimate. Each entry uses a descriptive `H3` heading followed by a 3-row table:

```markdown
### <descriptive title — e.g. "Legacy import path">

|  |  |
|---|---|
| **Rule** | R<N> |
| **Why** | <reason the deviation is justified> |
| **Tracked in** | <issue tracker ID, ADR reference, or "permanent — see Why"> |
```

Exceptions are temporary by definition — they exist to record an accepted current violation, and they are removed when the violation is fixed. They are not numbered: stable IDs are for things you cite from outside, and exceptions are referred to by their topic, not by an ID. When an exception is removed, the heading simply disappears; when the last exception goes away, drop the whole `## Known Exceptions` section with it.

The section is **optional**. Include it only when at least one intentional, accepted exception exists. Absence of the section means "no known exceptions today" — do not write `None.` or a placeholder.

A `## Known Exceptions` entry is the *only* legitimate way for code to violate a rule without changing the rule. An entry documents an **evaluated, accepted** deviation, not "we discovered some drift we haven't decided about yet." Unevaluated drift belongs in the issue tracker, not here. If the deviation is permanent, say so explicitly under `Tracked in:`. If the deviation is temporary, the tracker entry must hold the plan to remove it.

---

## Meta-rules — M1, M2, M3

The Definition of Done in [`definition-of-done.md`](definition-of-done.md) references three meta-rules. Their full rationale lives here so the per-component file does not have to repeat it.

### M1 — Coverage

Every active component must have a `DESIGN_RULES.md`. Every new active component (Django app, shared library, worker) added in a PR must include a `DESIGN_RULES.md` created in the same PR. If new behaviour added to an existing component falls outside the scope of any existing rule in that component's file, a new rule must be added in the same PR.

Why: a component without rules is a component that has been decided about in private. The point of this system is to make those decisions visible in the directory of the code they govern.

### M2 — Co-change

Any PR that changes behaviour governed by an existing `R1..Rn` rule must update the relevant rule(s) in the same PR. Both directions are blockers:

- Behaviour change without rule update → blocker (the rule is now stale).
- Rule update without behaviour change → blocker (the rule is now an unenforced wish).

M2 also covers ADR ID references: any PR that supersedes an ADR must update **every** reference to the old ADR ID anywhere in the repo (per-component `Refs:` rows, `principles.md`, `security/`, code comments, anywhere) in the same PR. The supersession itself is a delete — see `adr/README.md`.

Why: rules and code that drift apart silently are worse than no rules at all. They give reviewers a false sense of safety.

### M3 — Consistency

No rule in any `DESIGN_RULES.md` may contradict a rule in any other `DESIGN_RULES.md` or in `design-rules/`. If a PR creates a conflict, it must either edit one of the rules to reconcile, or add a new ADR that overturns the conflicting decision, **delete** the prior ADR in the same PR, and update every reference to the prior ADR ID across the repo to point at the new one (M2 above).

Why: a rule system that contradicts itself is no rule system at all. Reviewers cannot be expected to compute the consistent subset on every PR.

---

## When to update a per-component file

- Add a rule when a new model, manager, task, or sub-module is introduced inside that component.
- Update an existing rule when its `Refs:` line changes (a new ADR supersedes the old one, a principle is renumbered, a security standard shifts).
- Update or remove a rule when it stops describing reality. Removing a rule always leaves a gap in the numbering — never reuse the ID.
- Update `Enforced by:` whenever a new test or check starts covering the rule, or whenever an existing check is removed.
- Add a `Known Exceptions` entry when an intentional deviation lands in the code. Update or remove the entry when the deviation is resolved.
- Co-change with the code: M2 above. This is a hard rule, not a suggestion.

---

## When to add a per-component file

- Whenever a new active Django app is added under `backend/`, a new shared library directory is added under `unstract/`, or a new worker directory is added under `workers/`. M1 above.
- Copy the structure from a real, current file — `backend/account_v2/DESIGN_RULES.md` is the canonical reference.
- If the new component has no specific rules yet, the `## Rules` section contains a single line: `No component-specific rules yet.` The file is still mandatory; keep `## Checklist`, and include `## Known Exceptions` only when at least one accepted exception exists.

---

## What this contract intentionally does not say

- It does not list any specific rules. Those live in the per-component files.
- It does not list principles, ADRs, or security standards. Those live in `design-rules/principles.md`, `design-rules/adr/`, and `design-rules/security/`.
- It does not list debt or vulnerabilities. Those live in the project issue tracker and the project's private security channel.
- It does not name any specific PR review tool. The contract is generic: Claude Code, any future AI agent, and any human reviewer all read the same files.

---

## Self-update reminder

If you change this contract, expect to:

1. Update [`definition-of-done.md`](definition-of-done.md) if the change affects the checklist body, severity vocabulary, or M1/M2/M3 wording.
2. Update `.claude/skills/design-rules/scripts/validate.sh` if the Compatibility blockquote wording changes or the forbidden-word list needs adjusting — those are the literal strings the script currently greps for. (The script does not today enforce rule-format or section-header literals; if a future hardening pass adds those checks, list them here.)
3. Update `.claude/skills/design-rules/SKILL.md` if the contract introduces a new section that the `get` or `review` commands must surface.
4. Re-run `validate.sh` against every per-component file in the repo.
5. If the section structure itself changes, the change touches every per-component file. That is intentional: a structural change is a real event and a 41-file diff is the right blast radius.
