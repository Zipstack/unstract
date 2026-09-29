# Biome rule ratchet: warn now, error once clean

`biome.json` runs Biome's `recommended` set plus the React domain (hooks rules),
the whole `a11y` group and `noUnusedImports`. JSON allows no comments, so this
file records why some of those rules are `warn` and how each one becomes `error`.

## How severities are chosen

- **Recommended rules with no violations keep their default severity** — mostly
  `error`. They are enforced from day one, so nothing new can regress them.
- **Rules that already had violations are pinned to `warn`** in `biome.json`.
  `biome ci` does not fail on warnings, so CI stays green while the violations
  are burned down.
- **Every rule in the table below is headed for `error`**, whatever its
  default. `noUnusedImports` defaults to `warn`, so promoting it means setting it
  to `error` explicitly, not just deleting its entry.
- **Other recommended rules whose default is `warn` or `info`** (e.g.
  `noImportantStyles`, `noUnusedFunctionParameters`, `useLiteralKeys`) are left at
  that default and are not part of the ratchet.

## Both repos share this config

Cloud CI copies OSS `main`'s `frontend/`, overlays the cloud `src/plugins`, and
runs `biome ci src/plugins/` with this file. So a rule can only move to `error`
here once it is at **zero in OSS `src/` AND in cloud `src/plugins/`** — otherwise
the OSS change turns cloud `main` red with no cloud commit involved.

## Baseline

Measured with Biome 2.3.13 against OSS `f9dc6656` and cloud `7276f203`, after
this change. Only the rules pinned to `warn` are listed.

| Rule | OSS | Cloud | Follow-up |
|---|---:|---:|---|
| `correctness/useExhaustiveDependencies` | 431 | 530 | UN-4202 |
| `correctness/useHookAtTopLevel` | 15 | 10 | UN-4201 |
| `suspicious/noArrayIndexKey` | 8 | 28 | UN-4203 |
| `suspicious/noAssignInExpressions` | 13 | 1 | UN-4204 |
| `correctness/noUnusedImports` | 6 | 6 | UN-4204 |
| `suspicious/noShorthandPropertyOverrides` | 2 | 1 | UN-4204 |
| `security/noDangerouslySetInnerHtml` | 0 | 1 | UN-4204 |
| `a11y/noStaticElementInteractions` | 10 | 15 | UN-4194 |
| `a11y/noNoninteractiveElementInteractions` | 8 | 14 | UN-4194 |
| `a11y/useKeyWithClickEvents` | 5 | 14 | UN-4194 |
| `a11y/useSemanticElements` | 6 | 3 | UN-4194 |
| `a11y/useFocusableInteractive` | 3 | 0 | UN-4194 |
| `a11y/noLabelWithoutControl` | 2 | 0 | UN-4194 |
| `a11y/noRedundantRoles` | 2 | 0 | UN-4194 |
| `a11y/useAriaPropsSupportedByRole` | 1 | 0 | UN-4194 |
| `a11y/useButtonType` | 1 | 0 | UN-4194 |
| `a11y/useGenericFontNames` | 0 | 1 | UN-4194 |
| `a11y/useValidAnchor` | 0 | 1 | UN-4194 |

Reproduce a count (swap the rule; use `src/plugins/` in the cloud overlay):

```bash
cd frontend
bunx biome lint src/ --only=correctness/useHookAtTopLevel --max-diagnostics=none
```

## Order

1. **`useHookAtTopLevel`** (UN-4201) — a conditional hook call breaks React's hook order,
   so each hit is a potential bug, not style.
2. **Quick wins** (UN-4204) — small counts, mostly mechanical. `noUnusedImports` is a safe
   fix (`bun run check:fix`).
3. **a11y** (UN-4194) — the interaction rules share one cause: click handlers on
   `div`/`span`. Fixing each element usually clears three or four rules at once.
4. **`noArrayIndexKey`** (UN-4203) — give each list item a stable key.
5. **`useExhaustiveDependencies`** (UN-4202) — the bulk. Split it by area. Each fix changes
   when an effect runs, so review it as a behaviour change, not a lint fix.

## Promoting a rule

When a rule reaches zero in both repos, delete its `warn` entry from
`biome.json`, or set it to `error` if the rule's default is not `error`, in the
same PR as the last fix, and remove its row above. Land the cloud fixes first.

## Suppressions

Use `// biome-ignore <category>: <reason>` only where the code is deliberately
correct. Put it on the line before the hook or element Biome reports. The reason
must say why the code is right as written — "intentional" is not a reason.
`eslint-disable` comments do nothing under Biome; do not add them.
