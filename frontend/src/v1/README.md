# Frontend v1

The v1 frontend, built alongside v0 (everything else under `src/`) until v0 is
retired. The full guide is the Frontend Developer Guide for v1 (UN-4378); this
file holds only the rules that tooling enforces.

## Rules

- **TypeScript only.** `.ts` / `.tsx`, `strict`, unused locals and parameters
  are errors, no explicit `any`.
- **Nothing outside `src/v1`.** No v0 component, store, hook, helper, CSS or
  shim, and no symlinks. Import with `./` within a folder and `@v1/...` across
  folders; `../`, `/src/...` and `src/...` are never used.
- **v0 imports only the public entry**, `@v1` (`src/v1/index.ts`).
- **No PropTypes, no component `.css`, no antd** (package, shim or `ant-`
  class). Global v1 styles live in `styles/` and are imported as
  `@v1/styles/...`, including from inside `styles/`.

## Styling

- `ui:` on every utility: an unprefixed class renders with v0's theme whenever
  v0 already uses that class name, and silently does nothing otherwise. Merge
  with `cn` (`@v1/lib/cn`); `bun run tokens:v1` makes tokens.css from tokens.ts.
- Modes `light`, `dark`, `unstract` (or `system`): the user chooses, stored per
  browser under `unstract.v1.theme`, applied as `data-theme` by `ThemeProvider`.
  Portals: `getPortalContainer()`; focus: `ui:focus-visible:focus-ring`; Geist
  Mono only for model output, JSON and token counts.
- `lint:v1` S1–S8: no inline style, raw colour or pixel, `!important`, CSS
  import outside `app/` or `styles/`, selector outside `.v1`,
  `prefers-color-scheme` or unprefixed utility (code: class and colour strings).
  Pixel escape, CSS only: `/* v1-styles-allow: forced-colors outline */`.
- Known v0 rules that reach v1 (unlayered, so v1 loses without `!important`):
  - `scrollbar-color`, `::-webkit-scrollbar*`: the thumb stays light in dark.
  - `[data-radix-popper-content-wrapper] { z-index: 1500 !important }`.
  - `[data-sonner-toaster] { pointer-events: auto }`.

## Folders and what each may import

Every folder may import from itself. Test files (`*.test.ts(x)`,
`*.spec.ts(x)`) may also import `test/`.

| Folder | Holds | May import from |
| --- | --- | --- |
| `index.ts` | Public entry; the version switch (UN-4271) will mount v1 through it | everything |
| `app/` | Entry, providers, router, route registry | everything |
| `components/ui/` | Core components | `lib/`, `styles/` |
| `components/patterns/` | Composites built from core components | `components/ui/`, `lib/`, `services/`, `stores/`, `hooks/` |
| `shell/` | Top bar, rail, context bar, tab bar | `components/ui/`, `components/patterns/`, `services/`, `stores/`, `hooks/`, `lib/` |
| `pages/<page>/` | One folder per target page | `components/ui/`, `components/patterns/`, `shell/`, `services/`, `stores/`, `hooks/`, `lib/`, `styles/`, `plugins/` — not other pages, `app/`, `test/` or the entry |
| `services/` | Typed service modules; the only place a URL appears | `lib/` |
| `stores/` | Zustand stores | `lib/` |
| `hooks/` | Shared hooks | `lib/` |
| `lib/` | Pure helpers | — |
| `styles/` | Tokens and global v1 styles | `lib/` |
| `plugins/` | Cloud overlay target; empty in the public repository | everything |
| `test/` | Render helpers, fixtures, network mocks | everything |

## Scripts

| Script | Checks |
| --- | --- |
| `bun run typecheck:v1` | TypeScript-only files, CSS only in `styles/`, no symlinks, folder taxonomy; then `tsc` with `src/v1/tsconfig.json` |
| `bun run lint:v1` | Biome on `src/v1/`, then imports (nothing outside v1, folder contract, and v0 reaching v1 only through `@v1`), PropTypes and `ant-` checks, then the styling policy (S1 to S8 above) |
| `bun run tokens:v1` | Regenerates `styles/tokens.css` from `styles/tokens.ts` |
| `bun run test:v1` | v1 unit tests, then the guardrail fixtures in `test-fixtures/v1-boundary/` |

The v0 ↔ v1 boundary and the banned imports are Biome rules in `biome.json`,
so `biome ci src/` (CI) and editors report them too. The remaining checks are
`src/v1/tsconfig.json`, `scripts/check-v1.mjs` and `scripts/check-v1-styles.mjs`.
