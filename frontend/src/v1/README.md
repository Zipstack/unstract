# Frontend v1

The v1 frontend, built alongside v0 (everything else under `src/`) until v0 is
retired. The full guide is the Frontend Developer Guide for v1 (UN-4378). The
rules below are enforced by tooling unless marked as convention, and so is the
"May import from" column, for code and for CSS in `styles/`. The "Holds" column
is convention.

## Rules

- **TypeScript only.** `.ts` / `.tsx`, `strict`, unused locals and parameters
  are errors, no explicit `any`. Besides code, v1 holds only styles (in
  `styles/`), Vite asset types, JSON and Markdown; any other file type is
  rejected, since Vite can load any file (`?worker`).
- **Nothing outside `src/v1`.** No v0 component, store, hook, helper, CSS or
  shim, and no symlinks. Import with `./` within a folder and `@v1/...` across
  folders; `../`, `/src/...` and `src/...` are never used.
- **v0 imports only the public entry**, `@v1` (`src/v1/index.ts`).
- **Imports must be readable.** Use a string literal, or a template whose fixed
  prefix names the folder (`` `@v1/pages/${name}/index.tsx` ``, allowed only in
  folders that may import everything). In v1, an import of a variable, a
  concatenation or a template whose prefix has no `/` is rejected, and so is a
  `..` after a wildcard or `${}`, and a file that does not parse. v0 is judged
  by what Vite can resolve: a template, glob or concatenation by the fixed
  text it starts with; a bare variable is left alone, since Vite cannot bundle
  it.
- **No PropTypes, no component style files, no antd** (package, shim or
  `ant-` class). Style files are any CSS language Vite knows (`.css`, `.scss`,
  `.pcss`, …); CSS asset references include `image-set()` strings. Global v1 styles live in `styles/` and are imported as
  `@v1/styles/...`, including from inside `styles/`.
- **Static assets live in `assets/`**, imported as `@v1/assets/...` (e.g.
  `@v1/assets/logo.svg?react`). v1 never uses v0's `src/assets/` (enforced);
  where an asset file sits under v1 is convention, not checked.
- **Lucide is the only icon library**, imported by canonical name
  (`LoaderCircle`, not the `Loader2` alias) from `lucide-react` itself.
  `scripts/check-v1-icons.mjs` enforces it by package name: any other package
  whose name contains `icon` or `lucide`, a listed set whose name does not
  (`react-feather`, `@mdi/*`, `@fortawesome/*`, flag sets), every alias the
  installed lucide-react declares, and namespace, default, subpath,
  `icons`-map and dynamic imports all fail lint:v1, and so does a stylesheet
  `@import` of an icon package. A set outside the name
  rule and the list is not caught; add it to the script's list. Shared glyphs
  come by role from `lib/icons.ts`; provider logos, product marks and flags
  from `components/ui/BrandMark`.

## Styling

- `ui:` on every utility: an unprefixed class renders with v0's theme whenever
  v0 already uses that class name, and silently does nothing otherwise. Merge
  with `cn` (`@v1/lib/cn`); `bun run tokens:v1` makes tokens.css from tokens.json.
- Modes `light`, `dark`, `unstract` (or `system`): the user chooses, stored per
  browser under `unstract.v1.theme`, applied as `data-theme` by `ThemeProvider`.
  Portals: `getPortalContainer()`; focus: `ui:focus-visible:focus-ring`; Geist
  Mono only for model output, JSON and token counts.
- `lint:v1` S1–S8: no inline style, raw colour (hex, functions, palette or
  named, in code and CSS) or pixel (any length inside `[…]` or in CSS, `vh`
  and `vw` included), `!important`, CSS import outside `app/` or `styles/`,
  selector outside `.v1` (a sibling combinator right after the root,
  `.v1 + x` or `& ~ x` nested directly in the root, counts),
  `prefers-color-scheme`, or a utility without `ui:` first (`hover:ui:flex`
  compiles to nothing). Code: `className` values and `cn()`/`cva()` class
  positions always (a cva variant name or choice is not a class), other
  strings when they look like a class list.
  Runtime geometry: `style` may set only custom properties (`"--page-aspect"`,
  typed by `lib/css-custom-properties.d.ts`) that classes read
  (`ui:aspect-(--page-aspect)`); a plain key or a variable fails. Pixel
  escape, CSS only: `/* v1-styles-allow: forced-colors outline */`.
- Known v0 rules that reach v1 (unlayered, so v1 loses without `!important`):
  - `scrollbar-color`, `::-webkit-scrollbar*`: the thumb stays light in dark.
  - `[data-radix-popper-content-wrapper] { z-index: 1500 !important }`.
  - `[data-sonner-toaster] { pointer-events: auto }`.
  - `svg.lucide` under a `span`, `p`, `label`, `li`, `a`, `td` or `th` that
    is not `.flex`/`.inline-flex`/`.grid` (v0 names, so `ui:inline-flex`
    does not exempt) is forced to `1em` and `inline-block`, overriding the
    icon's `size` prop. Put icons in a `ui:flex`/`ui:inline-flex` parent
    that is not one of those tags, or size the parent's font.

## Feedback

- One notification entry point: `notify()` or `toast.success/error/warning/info`
  from `@v1/lib/notify`, which `services/` can reach too. The `Toaster` in
  `components/ui/feedback/` implements it; mount it once inside the v1 root.
  With no `Toaster` mounted, `notify()` only logs to the console (with the
  request id); nothing is shown or queued. `lint:v1` rejects sonner,
  react-hot-toast, react-toastify and notistack outside
  `components/ui/feedback/`, and there allows radix-ui only as a static named
  import that does not name `Toast` (Biome already rejects antd in v1).
- Errors are announced assertively, everything else politely. Toasts stack
  bottom-right (at most three), pause while hovered or focused, and F8 moves
  focus to them; pass `persistent` to keep one until it is dismissed. At the
  limit, timed toasts go before persistent ones; if all three are persistent
  the oldest goes. Reusing an `id` replaces a toast with a fresh one (new
  timer, announced again). A `requestId` is shown on the toast.
- Loading is a skeleton (`Skeleton` + `SkeletonText`, `SkeletonBlock`,
  `SkeletonAvatar`, `SkeletonTableRows`), never a spinner inside a card.
  `Spinner` sits only in buttons and running text. Errors on a screen are an
  `InlineAlert` above the content, with `onRetry`.

## Charts

- Line, area, bar, stacked bar and sparkline live in `components/ui/chart/`;
  its README has the props, colour ramp, marker rule and text alternative.
  Colours come from `--chart-1`…`--chart-5` and the semantic tokens only.

## Code and data

- Code, JSON, diffs, Markdown, copy controls and code editors come from
  `components/ui/code/` (`CodeBlock`, `JsonView`, `DiffView`, `Markdown`,
  `CopyButton`, `CodeEditor`, `InlineCode`); its README lists every prop.
  Do not build another highlighter, JSON tree, diff or Markdown renderer.
- Mono text (IDs, token counts) is `<InlineCode variant="plain">`; the font
  comes only from the `font-mono` token. Syntax and diff colours are the
  `code-*` and `diff-*` tokens.
- `CodeEditor` uses Monaco from its default CDN, as v0 does. Never call
  `loader.config()` in v1: the loader is shared with v0.

## Version switch and route registry

v0's router (`routes/Router.jsx`) wraps its routes in `VersionSwitch`, which
renders v1 for a URL whose page is live in the registry (`app/registry/`) and
v0 for everything else. v1 renders as its own tree (`app/V1App.tsx`), loaded
only when a v1 page first renders.

- **Declare** a page in `app/registry/entries.ts` (`PAGES`) with its v1 routes,
  the v0 routes it replaces and the mapping both ways, and add its component
  to `app/pages.ts`. Declared pages stay v0 for users.
- **Register** it, in its go-live task only (D9), by adding its key to
  `REGISTERED_PAGES`. Its v0 URLs then redirect to v1; reverting is that line.
  v1 renders outside v0's `PersistentLogin` and `RequireAuth`, and its own
  session and guards come with P0-T06: a page registered before that ships
  with no session load, login redirect or org check.
- `app/registry/validate.test.ts` fails CI on an invalid entry: overlapping
  patterns across pages, a v1 route and a different v0 route of one page that
  match the same URL (a page may keep its v0 URL), a route without a mapping
  to the other version, a page without a component, or `toggle` on any page
  but Human Review (UN11, D14) and its demo stand-in.
- Human Review's old-version preference is per user, per browser, in
  localStorage (`unstract.v1.oldVersion.<userId>`). `setOldVersion(on)` sets
  it, and the switch then moves the user to the mapped screen without a
  reload. `unstract.v1.lastUser` lets a reload apply it before the session
  loads; on a shared browser that is the previous user's choice until the
  session says otherwise.
- Until the v1 session lands (P0-T06), the switch learns the user only from
  v0's session, which v0 loads in `PersistentLogin`, a v0 route. A page load
  that starts on a v1 URL never loads it, so the switch has only
  `unstract.v1.lastUser`. With none (a fresh browser, or an E2E context
  signed in by API), `setOldVersion` returns false and changes nothing; with
  another person's, a choice made there is saved as theirs. Both last until a
  v0 page loads in that tab. E2E round trips seed `unstract.v1.lastUser` or
  open a v0 page first.
- `VITE_V1_DEV_ROUTES=true` (the E2E image, or `.env` locally) registers the
  demo pages (`/:orgName/v1-demo`, `/:orgName/v1-demo-review`, and their v0
  stand-ins `/:orgName/v0-demo…`). It also renders declared pages as v1 before
  they go live: set `localStorage["unstract.v1.preview"] = '["UN05"]'`, then
  reload (it is read when the app loads).
- `VITE_DISTRIBUTION` (`oss` by default, `cloud` or `onprem`) selects
  the build's distribution; entries whose `distributions` omit it are ignored.
  An unknown value fails `vite build`. P0-T07's plugin manifest (UN-4286)
  reads the same variable. The cloud and on-prem image builds do not set it
  yet, so every image builds as `oss`: until P0-T07 wires them, an entry that
  lists fewer than all three distributions is not filtered correctly there.

## Folders and what each may import

Every folder may import from itself. Test files (`*.test.ts(x)`,
`*.spec.ts(x)`) may also import `test/`.

| Folder | Holds | May import from |
| --- | --- | --- |
| `index.ts` | Public entry: the version switch and its helpers | everything |
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
| `bun run typecheck:v1` | TypeScript-only files, styles only in `styles/`, allowed file types only, no symlinks, folder taxonomy; then `tsc` with `src/v1/tsconfig.json` |
| `bun run lint:v1` | Biome on `src/v1/` (warnings fail), then imports in code and in `styles/` CSS (nothing outside v1, folder contract, and v0 reaching v1 only through `@v1`), PropTypes and `ant-` checks, the single notification entry point, then the styling policy (S1 to S8 above), then the icon rules |
| `bun run tokens:v1` | Regenerates `styles/tokens.css` from `styles/tokens.json` (via `styles/tokens.ts`; runs under bun, which imports the TypeScript source directly) |
| `bun run test:v1` | v1 unit tests (`vitest.v1.config.mts`, then cloud plugins with `vitest.v1-plugins.config.mts`) with v1's own coverage threshold, then the guardrail fixtures in `test-fixtures/v1-boundary/`, `test-fixtures/v1-harness/` and `test-fixtures/v1-unit-gate/` (the coverage threshold fails a run, and CI runs the rig group's config). The harness is documented in `test/README.md` |
| `bun run seam:v1` | Seam guard: v1 work changes v0 (`src/` outside v1, `public/`) only at the files in `scripts/v1-seam-allowlist.json`, compared with `origin/main` |
| `bun run separation:v1` | No enterprise plugin code: no folder under `plugins/` is tracked in the public repository |
| `bun run bundle:v1` | Production build, then no v1 module reaches a v0 module or antd through the imports Rollup resolved |

In CI these run as separate `v1 · …` checks (`.github/workflows/ci-frontend-v1.yaml`
and `ci-frontend-v1-seam.yaml`), apart from v0's checks. `lint:v1` and CI
fail on any Biome warning under `src/v1/`, and the accessibility rules are
errors there. A PR that is v1 work and needs a v0 change outside the seam
carries the `v0-change` label, which turns the seam check into a report.

Biome (`biome.json`) also reports the banned imports and the plain spellings of
the v0 ↔ v1 boundary, so `biome ci` and editors flag them too: `@/`, `../`,
`/src/` and `src/` in v1; `@v1/...`, `@/v1`, `src/v1`, `/src/v1` and relative
`./v1` / `../**/v1` in v0. The relative v0 patterns match any folder named
`v1`, so no v0 folder may take that name. Everything else (the folder
contract, templates, globs, `new URL`, CSS, symlinks) is checked only by
`scripts/check-v1.mjs`, the styling policy by `scripts/check-v1-styles.mjs`,
the icon rules by `scripts/check-v1-icons.mjs`, and types by `src/v1/tsconfig.json`.
