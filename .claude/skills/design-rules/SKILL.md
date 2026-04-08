---
name: design-rules
description: Manage and apply the file-based design rule system in this repo (design-rules/ and per-component DESIGN_RULES.md). Use when the user says "show design rules", "design rules for [component/path/file/PR]", "which rules apply to X", "add design rule", "add ADR", "update design rule", "review [code/PR] against design rules", "list ADRs", "list principles", or "validate design rules". Operations: list, get, add, update, review, validate.
compatibility: Designed for Claude Code. Requires git, gh, find, grep, ripgrep.
allowed-tools: Read Glob Grep Edit Write Bash(git:*) Bash(gh:*) Bash(find:*) Bash(grep:*) Bash(ls:*)
---

# Design Rules Skill

A skill for managing and applying the version-controlled design rule system in this repo. The system has two layers: global rules in `design-rules/` and per-component `DESIGN_RULES.md` files placed next to the code they govern, under `backend/`, `unstract/`, and `workers/` (where present). Coverage is rolled out incrementally — not every component has a file yet. The system is OSS-only — it must never reference cloud / enterprise / pluggable_apps / HITL / subscription / agentic / or any specific PR review tool.

---

## Quick Start

### Basic Commands

| What you want | What to say |
|---------------|-------------|
| List principles | "list principles", "list design principles" |
| List ADRs | "list ADRs", "show all ADRs" |
| List components with rules | "list components with rules", "which components have design rules" |
| Get rules for a file/dir/component | "design rules for backend/connector_v2", "which rules apply to api_v2/views.py" |
| Get rules for a PR or local diff | "design rules for PR #1902", "design rules for my changes" |
| Get all global rules | "show all design rules" |
| Add a new ADR | "add ADR for X" |
| Add a per-component rules file | "add DESIGN_RULES.md for backend/foo" |
| Update an existing rule | "update design rule for X", "rule about Y changed" |
| Review code against the rules | "review my changes against design rules", "check PR #1902 against design rules" |
| Validate the rule system itself | "validate design rules" |

### What you'll get

| Mode | Output |
|------|--------|
| **list** | Compact text list (titles + numbers, no bodies) |
| **get** | Deduped bundle: compatibility statement, relevant principles, AI Review Checklist, referenced ADRs, security standards, component Dos/Don'ts |
| **add** | New file written + cross-links updated; refused if content describes an aspiration rather than implemented behaviour |
| **update** | Minimal in-place edit; ADR superseded with a new ADR if the change is a reversal |
| **review** | Per-file findings table: file, line, principle/ADR violated, why, minimal fix |
| **validate** | Pass/fail report from forbidden-word grep, compatibility-statement check, ADR-link resolution |

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| **code-reviewer** | code-reviewer can call `design-rules review` to add design-rule checks on top of its SOLID/security review |
| **pr-creator** | pr-creator can call `design-rules get` to surface applicable rules in the PR description |
| **jira-manager** | jira-manager can call `design-rules get` when planning implementation of a ticket |
| **architecture-analyst** | architecture-analyst consults `design-rules/principles.md` and ADRs when documenting how a component works |

---

## Command: `list`

Show what rules exist, titles only — fast and cheap.

| Sub-command | Action |
|---|---|
| "list principles" | Read `design-rules/principles.md`, return P1–P9 titles only. |
| "list ADRs" | Read `design-rules/adr/README.md`. If missing, `ls design-rules/adr/ADR-*.md` and return numbers + titles. |
| "list components with rules" | `find backend unstract workers -name DESIGN_RULES.md`. Return grouped by directory. |
| "list global rules" | `ls design-rules/ design-rules/security/ design-rules/adr/`. |

Never dump full file bodies in `list` mode — that's `get`.

---

## Command: `get`

Fetch the rules that actually apply to a target.

**Steps:**
1. **Resolve the target paths.** Accept any of: a single file path, a directory, a component name (e.g. `connector_v2`), a glob, or a list of files (from `gh pr diff <n> --name-only` or `git diff --name-only`).
2. **For each target file**, walk from the file's directory upward to the repo root and collect every `DESIGN_RULES.md` along the way. Always include `design-rules/README.md`, `design-rules/principles.md`, and `design-rules/ai-review-checklist.md`.
3. **Read the collected files** and present them in this order:
   - Compatibility statement (once)
   - Principles referenced by any collected component file's "Read first"
   - AI Review Checklist (always)
   - ADRs referenced by any collected component file
   - Security standards referenced (e.g. `security/tenant-isolation.md`, `security/standards.md`, the inline SQL Safety Standard under `unstract/connectors/.../databases/`)
   - The component-specific Dos / Don'ts / Acceptance criteria from each collected `DESIGN_RULES.md`
4. **Deduplicate.** Never show the same principle or ADR twice.
5. If asked for "all" design rules, dump the global files (`design-rules/**`) without per-component noise.

---

## Command: `add`

Create a new rule, ADR, or per-component file.

**Gate before adding anything:** verify the content describes current implemented behaviour, not aspirations. The system explicitly excludes unimplemented designs (no AuditLog table, no SoftDeleteMixin, no proposed key/role architecture, etc.). If the user wants to record an aspiration, push back and suggest the issue tracker or Confluence instead.

### Add a global principle or refinement
- New principle → edit `design-rules/principles.md`, take the next free `P<N>` number, **and** update `design-rules/ai-review-checklist.md` in the same change to add a question for it.
- Refinement of an existing principle → edit it in place; do not duplicate.

### Add an ADR
1. `ls design-rules/adr/ADR-*.md` to find the next free number (the highest existing number plus one — never fill a gap).
2. Create `design-rules/adr/ADR-NNN-<kebab-title>.md`:
   ```markdown
   # ADR-NNN: <title>

   ## Context
   <why this decision is needed; what's currently true>

   ## Decision
   <what was decided>

   ## Consequences
   <what becomes easier / harder / required>
   ```
   There is no `Status` field — the merge IS the acceptance. See `design-rules/adr/README.md` for the full ADR format and the delete-on-supersession flow.
3. Add a one-line entry to the Index table in `design-rules/adr/README.md`.
4. Cross-link from the relevant per-component `DESIGN_RULES.md` files in their `Read first` section.

### Add a per-component `DESIGN_RULES.md`
1. Verify the directory exists on disk and contains real source (not just `__pycache__`).
2. Use the standard template from `design-rules/README.md`. Always include the verbatim compatibility statement.
3. Include "Read first" links to `principles.md`, `ai-review-checklist.md`, and any relevant ADRs / security standards.
4. If the component has no specific Dos / Don'ts in source material, write the boilerplate body with `No component-specific rules beyond the global principles.`

---

## Command: `update`

Apply new changes to existing rules. Triggered by "update design rule for X", "the rule about Y changed", or when implementation drift is detected during review.

1. Identify the affected files: principle file, ADR(s), per-component file(s).
2. Make minimal edits in place. Never duplicate content between global and component files.
3. If a previously-recorded rule is now wrong because the implementation changed, **update the rule, do not add a contradicting one**. If the change is significant enough to be a decision reversal, add a new ADR that overturns the prior decision and **delete** the old ADR in the same PR — update every reference to the old ADR ID repo-wide (M2). See `design-rules/adr/README.md` for the full supersession flow.
4. If a per-component file is updated, also check whether the global ADR / principle / security standard it references still matches. Fix upstream first if both are wrong.

---

## Command: `review`

Check code or a diff against the design rules. Triggered by "review against design rules", "check this PR against design rules", "does X violate any rule".

1. **Determine the target.** Accept: a list of changed files, a PR number (use `gh pr diff <n> --name-only`), `git diff --name-only` for local changes, or a single file.
2. **Run `get`** on those targets to collect all applicable rules.
3. **For each changed file**, walk through the AI Review Checklist questions (`design-rules/ai-review-checklist.md`) and the component's Dos / Don'ts. For every violation, output:
   - File and line (when known)
   - Principle / ADR / security standard violated
   - Why it's a violation
   - Minimal fix
4. **Pay special attention to known traps:**

   | Trap | What to look for | Reference |
   |---|---|---|
   | Tenant isolation bypass | New model or queryset bypassing org scoping | `security/tenant-isolation.md` (Three-Layer Defense) |
   | SQL injection | String interpolation into SQL inside `unstract/connectors/.../databases/**` | inline SQL Safety Standard S1 in that directory's `DESIGN_RULES.md` |
   | Missing auth | New endpoint without authentication | P5 fail-closed |
   | Direct org FK on derived model | New model that doesn't inherit org through a parent | P6, ADR-002 |
   | Audit/billing CASCADE | New audit/billing record using FK CASCADE to parent | P4, ADR-003 |
   | Credential duplication | Storing the same credential twice instead of referencing | P2 |

5. **Do not invent rules.** If a pattern looks suspicious but no rule covers it, say so explicitly and recommend opening a tracker entry instead of pretending a rule exists.

---

## Command: `validate`

Sanity-check the rule system itself. Triggered by "validate design rules", "check design rules consistency".

Run the bundled script from the repo root:

```bash
.claude/skills/design-rules/scripts/validate.sh
```

The script checks: forbidden-word scan, compatibility-statement presence in every per-component file, and that each per-component file's directory contains real source. Exit code 0 = clean; 1 = problems found. Report any hits as fix-required and offer to fix them in place.

---

## What this skill must NOT do

- Never add debt items, vulnerability reports, or open design questions to the repo. Those belong in the issue tracker and the private security channel.
- Never document a proposed / unimplemented design as if it were a rule.
- Never name a specific PR review tool inside any rule file.
- Never duplicate global rule content into per-component files.
- Never create a `DESIGN_RULES.md` for `pluggable_apps/*`, `workers/pluggable_worker`, or `frontend/`.

---

## Path reference

| Path | Purpose |
|---|---|
| `design-rules/README.md` | Entry point: navigation, how-to recipes, and the AI-loading instruction (load `DESIGN_RULES.md` from the dir of any changed file). |
| `design-rules/principles.md` | P1–P9. |
| `design-rules/ai-review-checklist.md` | 9 questions every change must answer "yes" to. |
| `design-rules/lifecycle.md` | Design → assembly → deploy → runtime → monitoring. |
| `design-rules/security/tenant-isolation.md` | Three-Layer Defense. |
| `design-rules/security/standards.md` | SQL Safety S1 + current protection patterns as rules. |
| `design-rules/adr/ADR-*.md` | 8 accepted ADRs. |
| `unstract/connectors/src/unstract/connectors/databases/DESIGN_RULES.md` | SQL Safety Standard S1 inlined for the 8 DB connectors. |
| `backend/**/DESIGN_RULES.md` | Per-Django-app component files (where present). |
| `unstract/**/DESIGN_RULES.md` | Per-shared-lib component files (where present). |
| `workers/**/DESIGN_RULES.md` | Per-worker component files (where present). |
