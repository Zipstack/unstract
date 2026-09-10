# P0 — shadcn/ui Foundation

Implements **P0-01 … P0-16** of `UN_SHADCN_IMPL_PLAN.md`
(spec: `UN_SHADCN_SPEC.md`, palette decision **D8** = Midnight Bloom).

**Zero visual change is the goal of this phase.** antd still renders every
screen; this PR only installs the shadcn stack alongside it (§7 coexistence).

---

## What landed

| Task | Change |
|---|---|
| P0-03/04 | shadcn stack + Radix + RHF/zod + self-hosted `@fontsource` Inter / Geist Mono |
| P0-05 | `components.json` (`style: new-york`, `tsx: false`, lucide) |
| P0-06 | `tailwind.config.js`, `postcss.config.js` |
| P0-07 | `@tailwindcss/vite` added **after** `optionalPluginImports()` |
| P0-08 | `src/lib/utils.js` — `cn()` |
| P0-09 | Legacy CSS vars → `--legacy-*` (D6) |
| P0-10/11/12 | `src/index.css`: Tailwind first, Midnight Bloom tokens, `@theme inline` |
| P0-13 | 32 primitives in `src/components/ui/` |
| P0-14 | `vitest.config.mjs`: `@` alias + `css: false` |
| P0-15 | `next-themes` `ThemeProvider` driven by the existing session theme |
| P0-16 | `sonner` `<Toaster />` + shared `useAppToast` helper |

## Gate results

| Gate | Result |
|---|---|
| **P0-G1** build w/o plugins | **PASS** — `src/plugins/` is absent in an OSS checkout by design (copy overlay, gitignored), so every build here exercises the `optionalPluginImports` path |
| **P0-G3** dark mode | **PASS** — see below |
| **P0-G4** lint | **PASS** (see "Pre-existing" note) |
| **P0-G5** tests | **PASS** — 4 files / 16 tests green |
| **P0-G6** no visual regression | **PASS** — see below |

### P0-G3 — `@theme inline` verified

Measured in headless Chromium by toggling `.dark` on `<html>`:

| | light | dark |
|---|---|---|
| `--background` | `#fafafa` | `#1a1a1a` |
| `--foreground` | `#1a1a1a` | `#fafafa` |
| **`bg-background` utility** | `rgb(250,250,250)` | `rgb(26,26,26)` |
| **`text-foreground` utility** | `rgb(26,26,26)` | `rgb(250,250,250)` |

The last two rows are the ones that matter: the **Tailwind utilities** flip, not
just the CSS variables. A plain `@theme` would have frozen them at the light
value — this is the trap called out in §2.5.3a.

`--primary` is `#6f5cef` in both modes (correct — Midnight Bloom keeps the
brand violet constant across themes).

### P0-G6 — no visual regression

Same page measured before and after P0:

| Metric | Before | After |
|---|---|---|
| antd elements | 33 | 33 |
| antd buttons | 5 | 5 |
| button height | 50px | 50px |
| button background | `rgb(47,147,246)` | `rgb(47,147,246)` |
| button radius | 6px | 6px |
| body background | `rgb(233,233,233)` | `rgb(233,233,233)` |
| body font | system | **Inter** |

Only the font changed — that is P0-12's intended effect. Tailwind Preflight does
not disturb antd, consistent with the coexistence test in §7.

---

## Notes for review

**Two deviations from the plan, both necessary and neither changing intent:**

1. **`jsconfig.json` added** (not in the plan). The shadcn CLI refuses to run
   without it: *"Failed to load jsconfig.json. Couldn't find tsconfig.json"*. It
   declares the same `@/*` → `./src/*` alias that `vite.config.js` already has,
   so it also fixes editor/IDE resolution.

2. **`biome.json` — `css.parser.tailwindDirectives: true`** (not in the plan).
   Without it Biome cannot parse `@theme` / `@plugin` / `@custom-variant` and
   **fails CI with 4 CSS parse errors**. This is a required companion to
   adopting Tailwind v4; the plan's P0-G4 gate missed it.

**Pre-existing lint findings (NOT introduced here):** `biome ci src/` reports 4
errors and 26 warnings. All 4 errors are in `src/assets/export-tool.svg` and
`src/assets/login-onboard-message.svg`; both files are byte-identical to `main`,
and running the same Biome binary against a pristine `main` checkout reproduces
them. The 26 warnings (`noEmptyBlockStatements`, `useBlockStatements`) are in
files this PR never touched.

**Deferred deliberately:**
- `body { overflow: hidden }` is left as-is. It interacts with Radix's
  scroll-lock; P0-12 says re-test at the first P2 dialog conversion.
- `ALERT_SURFACE = "antd"` in `App.jsx` keeps antd as the single notification
  surface. The sonner bridge is mounted and wired but dormant, so alerts are not
  double-rendered. P2-06 flips the constant and deletes the antd branch.

**Not started:** P1–P4 and the cloud plugin phase, per the 🛑 STOP gate after P0.
