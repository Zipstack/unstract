# Design Rules

This directory holds the version-controlled architectural rules for this repository. The goal is for any AI agent or reviewer to be able to load the rules that apply to a change without leaving the repo.

> **Instructions for AI agents and PR review bots.** AI agents and PR review bots working on this repository must load `DESIGN_RULES.md` from the directory of any file being changed (and from each parent directory up to the repo root). Together with `principles.md` and `ai-review-checklist.md`, those files define the rules every change must respect. If a directory does not contain a `DESIGN_RULES.md`, only the global rules in this directory apply.

This nested-discovery pattern follows the [AGENTS.md](https://agents.md/) convention; `DESIGN_RULES.md` is a structured dialect of it, with the schema defined in [`per-component-contract.md`](per-component-contract.md).

---

## Layout

| File | Purpose |
|---|---|
| [`principles.md`](principles.md) | Universal principles P1–P9 |
| [`ai-review-checklist.md`](ai-review-checklist.md) | 9 questions to answer on every change |
| [`lifecycle.md`](lifecycle.md) | Change lifecycle from design to monitoring |
| [`security/tenant-isolation.md`](security/tenant-isolation.md) | Three-Layer Defense |
| [`security/standards.md`](security/standards.md) | SQL safety and current protection patterns |
| [`adr/`](adr/) | Accepted Architecture Decision Records |

---

## How to add a global rule

| Step | Action |
|---|---|
| 1 | Decide whether the rule is universal (goes in `principles.md`) or a security standard (goes in `security/standards.md`). |
| 2 | Open a PR. The rule must describe behaviour that is implemented in current code, not aspirational. |
| 3 | Update `ai-review-checklist.md` if the rule needs a checklist question. |

---

## Per-component `DESIGN_RULES.md` template

Every active component (each Django app under `backend/`, each `unstract/` shared library, each worker under `workers/`) holds a `DESIGN_RULES.md` at its directory root. The canonical shape is defined in one place and copied from one place — do not embed a duplicate template here.

| What you need | Where to find it |
|---|---|
| The authoritative spec (section structure, rule format, severity vocabulary, Known Exceptions, M1/M2/M3) | [`per-component-contract.md`](per-component-contract.md) |
| A concrete file to copy when creating a new component's rules | [`backend/account_v2/DESIGN_RULES.md`](../backend/account_v2/DESIGN_RULES.md) |
| The canonical Definition of Done | [`definition-of-done.md`](definition-of-done.md) |

If `per-component-contract.md` and an example file ever disagree, the contract wins.

---

## How to add an ADR

| Step | Action |
|---|---|
| 1 | Pick the next free `ADR-NNN` number under `adr/`. |
| 2 | Use the format: Status / Context / Decision / Consequences. |
| 3 | Only ADRs with status "Accepted" land here. Proposals live elsewhere. |
| 4 | Link the ADR from any per-component `DESIGN_RULES.md` it constrains. |

---

## Where debt is tracked

Technical debt is tracked in the project issue tracker, not in this repository.

## Where vulnerabilities are tracked

Security vulnerabilities are tracked in the project's private security channel, not in this repository.
