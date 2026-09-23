# antd → shadcn conversion: shim vs direct swap

Convention for the whole migration. Decided during P1-03/P1-04; applies to every
remaining component in P1–P4 and to Phase C (cloud plugins).

## The decision rule

For each antd component, ask: **does it implement behaviour that the shadcn
primitive does not?**

- **Yes → write a shim.** `src/components/ui/antd-<component>.jsx`, presenting
  antd's prop API on top of the shadcn primitive + Midnight Bloom tokens.
  Call-sites then change by import only, so the JSX is untouched: same
  elements, same order, same props. That is what C4 requires.
- **No (styling only) → direct swap.** Replace the element and express the
  styling as Tailwind utilities. No shim, no indirection.

Silently dropping behaviour is a **regression, not a restyle**, and C4 forbids
it. When in doubt, grep the call-sites for the behavioural props before deciding
— the counts have repeatedly contradicted intuition.

## Naming

| Kind | Path | Exports |
|---|---|---|
| Compatibility shim | `@/components/ui/antd-<name>.jsx` | antd's API |
| Pure shadcn primitive | `@/components/ui/<name>.jsx` | shadcn's API |

The `antd-` prefix is deliberate: it marks the file as **migration debt with an
exit**, and makes it obvious in review when new code reaches for the
compatibility layer instead of the primitive.

**New code should import the plain primitive.** The `antd-*` modules exist to
carry existing call-sites across without behaviour drift.

## Every shim needs

1. A header comment stating **which behaviours** justify its existence, with
   usage counts.
2. Unit tests covering **exactly those behaviours** — not just "it renders".
   The test suite is the proof that nothing was silently dropped.
3. A line in the table below.

## Decisions so far

| antd | Files | Call | Why |
|---|---|---|---|
| `Typography` | 93 | **Shim** | `ellipsis={{ tooltip, rows }}` (12 sites) truncates *and* shows full text on hover / clamps lines. Tailwind `truncate` is CSS-only. |
| `Button` | 70 | **Shim** | `loading` (234) swaps a spinner *and disables*; `icon` (106) is a slot; `danger` (12) is orthogonal to `type`; `htmlType` → DOM `type`. |
| `@ant-design/icons` | 91 | **Direct swap** | Pure glyph substitution. Mapping table in `icon-map.md`; three name collisions needed aliases. |

## Planned (from the re-measured counts)

**Shim** — behaviour antd implements and shadcn does not:

| antd | Files | Behaviour at stake |
|---|---|---|
| `Modal` | 40 | `Modal.confirm`/`info` static methods, `destroyOnClose`, `afterClose`, footer conventions |
| `Select` | 21 | `showSearch`, `mode="multiple"`, `filterOption`, `labelInValue` — Radix Select has none |
| `Table` | 16 | antd's is feature-complete; shadcn's is presentational (see D5 / TanStack) |
| `Form` | 16 | validation + layout + state in one component; RHF splits them (P3, pattern-first) |
| `Popconfirm` | 8 | routed through the shared `useConfirm()` hook (P2-01) |
| `Upload` | 4 | `beforeUpload`, `customRequest`, file-list state |

**Direct swap** — styling only:

`Space` / `Row` / `Col` / `Flex` (124 combined) · `Card` (20) · `Tag` (16) ·
`Divider` (9) · `Avatar` (7) · `Empty` (7) · `Progress` (2)

**Check first:** `Spin` (10) — bare `<Spin />` is a direct swap to `Spinner`,
but `<Spin spinning={x}>{children}</Spin>` is an overlay wrapper, which is
behaviour. Grep before deciding.

### `Space` is the one trap in the "direct swap" list

`<Space>` wraps **each child in its own `<div>`** and injects gaps between them.
Replacing it with `gap-*` on the parent removes those wrapper divs, so any CSS
selector matching `> *` against them will stop applying. Before converting,
check `Space` sites whose children come from `.map()` or conditional renders.

## Exit story

The `antd-*` shims are not permanent. Once P4 removes antd:

- `antd-button` / `antd-typography` can be unwound by migrating call-sites to
  the plain primitives, or kept as the app's own convenience layer — a decision
  worth making *after* the migration, not during it.
- Either way they must not grow new antd-only props. If a converted call-site
  needs something the shim lacks, prefer changing the call-site.
