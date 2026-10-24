# Frontend v1

v1 is rebuilt beside v0 and cannot touch it. TypeScript only, strict, with its own import alias `@v1/`.

## Folders

| Folder | Holds | May import from |
|---|---|---|
| `app/` | Entry, providers, router, route registry | everything under `v1/` |
| `components/ui/` | Core components | `lib/`, `styles/`, other `ui/` components |
| `components/patterns/` | Composites built from core components | `ui/`, `lib/`, `services/`, `stores/`, `hooks/` |
| `shell/` | Top bar, rail, context bar, tab bar | `ui/`, `patterns/`, `services/`, `stores/`, `hooks/`, `lib/` |
| `pages/<page>/` | One folder per target page | everything except other pages |
| `services/` | Typed service modules, one per backend resource; the only place a URL appears | `lib/` |
| `stores/` | Zustand stores | `lib/` |
| `hooks/`, `lib/`, `styles/` | Shared hooks, pure helpers, tokens and global v1 styles | `lib/` only |
| `plugins/` | Cloud overlay target; empty in the public repository | everything under `v1/` |
| `test/` | Render helpers, fixtures, network mocks | everything under `v1/` |

## Rules

`bun run lint:v1` and `bun run typecheck:v1` fail on each of these:

- A v1 file imports anything outside `src/v1/`. A v0 file imports anything under `src/v1/` other than `src/v1/index.ts`.
- A `.js`, `.jsx`, `.mjs` or `.cjs` file under `v1/`, or a `.css` file outside `styles/`.
- `prop-types`, `antd` or `@ant-design/*`, an `ant-` class name, or an explicit `any`.
- A relative import that crosses folders. Use `@v1/<folder>/...` instead.
- Unused locals, imports and parameters.

A type needed by both v0 and v1 is defined again in v1, never shared.

## Scripts

| Script | Runs |
|---|---|
| `bun run typecheck:v1` | File-type check, then `tsc -p tsconfig.v1.json` |
| `bun run lint:v1` | Biome on `src/v1`, then the import boundary in both directions |
| `bun run test:v1` | Vitest on `src/v1`, then the boundary script's own fixtures |

The v0 scripts (`typecheck`, `lint`, `test`, `build`) behave as before.

`tsconfig.v1.json` extends the root config, which excludes `src/v1`, so it restates `exclude`. Its `paths` replaces the root's `@/*`, so a v1 file cannot reach v0 through that alias either.
