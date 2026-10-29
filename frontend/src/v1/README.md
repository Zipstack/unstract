# Frontend v1

The v1 frontend, built alongside v0 (everything else under `src/`) until v0 is
retired. The full guide is the Frontend Developer Guide for v1 (UN-4378). The
rules and the "May import from" column below are enforced by tooling; the
"Holds" column is convention.

## Rules

- **TypeScript only.** `.ts` / `.tsx`, `strict`, unused locals and parameters
  are errors, no explicit `any`.
- **Nothing outside `src/v1`.** No v0 component, store, hook, helper, CSS or
  shim, and no symlinks. Import with `./` within a folder and `@v1/...` across
  folders; `../`, `/src/...` and `src/...` are never used.
- **v0 imports only the public entry**, `@v1` (`src/v1/index.ts`).
- **Imports must be readable.** Use a string literal, or a template whose fixed
  prefix names the folder (`` `@v1/pages/${name}/index.tsx` ``, allowed only in
  folders that may import everything). An import of a variable is rejected.
- **No PropTypes, no component `.css`, no antd** (package, shim or `ant-`
  class). Global v1 styles live in `styles/` and are imported as
  `@v1/styles/...`, including from inside `styles/`.
- **Static assets live in `assets/`**, imported as `@v1/assets/...` (e.g.
  `@v1/assets/logo.svg?react`). v1 never uses v0's `src/assets/`.

## Folders and what each may import

Every folder may import from itself. Test files (`*.test.ts(x)`,
`*.spec.ts(x)`) may also import `test/`.

| Folder | Holds | May import from |
| --- | --- | --- |
| `index.ts` | Public entry; the version switch (UN-4271) will mount v1 through it | everything |
| `app/` | Entry, providers, router, route registry | everything |
| `components/ui/` | Core components | `lib/`, `styles/`, `assets/` |
| `components/patterns/` | Composites built from core components | `components/ui/`, `lib/`, `services/`, `stores/`, `hooks/`, `assets/` |
| `shell/` | Top bar, rail, context bar, tab bar | `components/ui/`, `components/patterns/`, `services/`, `stores/`, `hooks/`, `lib/`, `assets/` |
| `pages/<page>/` | One folder per target page | `components/ui/`, `components/patterns/`, `shell/`, `services/`, `stores/`, `hooks/`, `lib/`, `styles/`, `assets/`, `plugins/` — not other pages, `app/`, `test/` or the entry |
| `services/` | Typed service modules; the only place a URL appears | `lib/` |
| `stores/` | Zustand stores | `lib/` |
| `hooks/` | Shared hooks | `lib/` |
| `lib/` | Pure helpers | — |
| `styles/` | Tokens and global v1 styles | `lib/`, `assets/` |
| `assets/` | Static files: icons, logos, images (and a generated icon map) | — |
| `plugins/` | Cloud overlay target; only a placeholder in the public repository | everything |
| `test/` | Render helpers, fixtures, network mocks | everything |

## Scripts

| Script | Checks |
| --- | --- |
| `bun run typecheck:v1` | TypeScript-only files, CSS only in `styles/`, no symlinks, folder taxonomy; then `tsc` with `src/v1/tsconfig.json` |
| `bun run lint:v1` | Biome on `src/v1/`, then imports (nothing outside v1, folder contract, and v0 reaching v1 only through `@v1`), PropTypes and `ant-` checks |
| `bun run test:v1` | v1 unit tests, then the guardrail fixtures in `test-fixtures/v1-boundary/` |

The v0 ↔ v1 boundary and the banned imports are Biome rules in `biome.json`,
so `biome ci src/` (CI) and editors report them too. The remaining checks are
`src/v1/tsconfig.json` and `scripts/check-v1.mjs`.
