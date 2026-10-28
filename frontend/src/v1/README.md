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

- Utilities carry the `ui:` prefix (`ui:bg-background`): v0's stylesheet also
  scans `src/v1`, so an unprefixed class renders with v0's theme. Merge with
  `cn` from `@v1/lib/cn`. Tokens live in `styles/tokens.ts`; `tokens.css` is
  generated from them by `bun run tokens:v1`.
- `ThemeProvider` sets `data-theme` (`light`, `dark`, `unstract`; key
  `unstract.v1.theme`); portals use `getPortalContainer()`. `ui:focus-ring` is
  the one focus style; Geist Mono only for model output, JSON and token counts.
- `lint:v1` rejects: S1 inline `style`; S2 raw colours; S3 raw pixel values;
  S4 `!important`; S5 CSS imports outside `app/` and `styles/`; S6 selectors
  not starting with `.v1`; S7 `prefers-color-scheme` in CSS; S8 unprefixed
  utilities. In code, S2 to S4 and S8 read class strings only (`className`
  values, `cn()`/`cva()` arguments, constants holding classes), not every string.

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
