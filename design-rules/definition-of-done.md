# Definition of Done (per-component changes)

This file is the single source of truth for the per-component Definition of
Done. Every per-component `DESIGN_RULES.md` ends with a `## Checklist` section
that links here. The body of the checklist lives only in this file.

A change governed by a per-component `DESIGN_RULES.md` is ready to merge when
**all** of the following are true:

- [ ] Every rule R1..Rn in the affected file passes for the changed code
- [ ] Every rule's `Enforced by:` mechanism actually runs on this PR
      (test, middleware, CI check, or `code review only`)
- [ ] The global AI Review Checklist
      (`design-rules/ai-review-checklist.md`) answers "yes" to every
      applicable question
- [ ] **M1 (coverage):** if a new sub-component, model, or task was added,
      it is covered by a rule in the affected file
- [ ] **M2 (co-change):** if behaviour governed by R1..Rn changed, the
      relevant rule(s) were updated in this same PR
- [ ] **M3 (consistency):** no rule in the affected file contradicts a rule
      in any other `DESIGN_RULES.md` or in `design-rules/`
- [ ] If a previously-listed rule is being removed or weakened, a new ADR
      justifies it; the prior ADR — if any — is **deleted** in the same PR
      and every reference to its ID across the repo is updated (see
      `adr/README.md`)
- [ ] Any intentional violation is recorded as a `## Known Exceptions` entry
      in the affected file, with a tracker reference

## Why this is one file

Inlining the same eight-line block in 41 per-component files is duplicated
boilerplate that drifts the moment any line of it changes. Reviewers learn
this checklist once. The per-component file's `## Checklist` section is a
single line that links here.

## Severity vocabulary used by rules

Rules in per-component files carry one of three RFC 2119 severities. The
checklist above applies to MUST and SHOULD rules; MAY rules are advisory.

| Severity | Meaning | Reviewer behaviour |
|---|---|---|
| **MUST** | The rule is non-negotiable. A violation is a merge blocker unless an ADR supersedes the rule or a `Known Exceptions` entry justifies the deviation. | Block the PR. |
| **SHOULD** | The rule reflects strong consensus. A violation is allowed only with a documented reason in the PR description and, if recurring, a `Known Exceptions` entry. | Request changes; accept with explicit justification. |
| **MAY** | The rule is a recommended default. A violation is fine without justification but should still be a conscious choice. | Note in review; do not block. |

If a rule has no severity tag, the reviewer treats it as MUST. Default to the
strictest reading.
