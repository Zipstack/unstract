# Selection inputs

The one way v1 picks from a list: dropdowns, searchable pickers, chip inputs
and segmented switches (P1-T04, UN-4301). Import everything from
`@v1/components/ui/select`:

```tsx
import {
  Chip,
  Combobox,
  type LoadOptions,
  MultiSelect,
  SegmentedControl,
  Select,
  type SelectOption,
} from "@v1/components/ui/select";
```

| Component | Use it for | Size |
| --- | --- | --- |
| `Select` | One choice from a short, known list | 32 tall; under about 50 options |
| `Combobox` | One choice from a long or server-loaded list, by typing | 32 tall; any length, virtualised past 100 |
| `MultiSelect` | Several choices, shown as chips | 32 tall, grows as chips wrap; any length, virtualised past 100 |
| `SegmentedControl` | Exactly one of a few always-visible options | 32 tall; 2 to 5 options |
| `Chip` | A selected value with a remove button (MultiSelect uses it) | 20 tall |

## Rules

- **The trigger is the field frame.** `Select`, `Combobox` and `MultiSelect`
  use the P1-T03 `FieldFrame` recipe verbatim (`TRIGGER_FRAME` in
  `trigger.ts`: 32 tall, radius 8), so a select and a text input sit
  identically in a form. `MultiSelect` swaps the fixed height for
  `min-h-8` and wraps its chips. Only `Select`'s trigger is
  `cursor-pointer`: it is a button, while the Combobox and MultiSelect
  frames hold a text input.
- **Pick by list size.** `Select` (Radix Select) renders every option, so it
  is for lists under about 50 options. Longer lists, and anything loaded from
  the server, use `Combobox` (or `MultiSelect` for several values), which
  filter as you type and, past `VIRTUALIZE_ABOVE` = 100 options, render only
  the rows in view (`@tanstack/react-virtual`). `Select` never virtualises and
  has no `loading` prop. Past five always-visible options, a
  `SegmentedControl` becomes a `Select`.
- **One option model.** Every component takes `SelectOption`:

  ```ts
  type SelectOption = Readonly<{
    value: string;
    label: string;
    description?: string;   // a second line, in the caption role
    leading?: ReactNode;    // a lucide icon or <ProviderLogo decorative … />
    disabled?: boolean;
    keywords?: readonly string[]; // extra words the filter matches
  }>;
  ```

  `keywords` feed the Combobox and MultiSelect filter (a case-insensitive
  substring of the label or any keyword, e.g. a model id); type-ahead in
  `Select` matches labels only. Logos go in `leading`:
  `leading: <ProviderLogo provider={adapter.id} name={adapter.name} decorative />`
  from `@v1/components/ui/BrandMark` (decorative, because the label beside it
  already names it). A row is 32 tall, or 48 with a description.
- **One list surface.** Every popover list is `LIST_SURFACE`: the popover
  colour, radius 10 (`rounded-lg`), `shadow-md` (board § 6, "dropdown
  menus"), at least 192 wide and the trigger's width, at most 320 tall. It is
  a flex column with hidden overflow and exactly **one** scroll element
  inside: Radix Select's Viewport, or the `Listbox` scroll element for the
  Popover lists. In the Popover lists the status rows ("Loading…", "No
  options" or "No matches", "Could not load options") are `<output>`
  elements beside the `role="listbox"` element, never inside it, since a
  listbox may hold only options. (`Select`'s "No options" row is also an
  `<output>`, in Radix's Viewport, shown only when the list is empty.)
- **Combobox pattern.** `Combobox` and `MultiSelect` follow the ARIA
  combobox-with-listbox pattern: focus stays on the input (`role="combobox"`,
  `aria-expanded`, `aria-controls`, `aria-autocomplete="list"`), which points
  at the active `role="option"` with `aria-activedescendant`; no live region.
  Each option's id is tied to its value, not its index, so when typing
  changes the first match the active id changes and a screen reader
  announces it. The listbox takes the field's `aria-labelledby` (or
  `aria-label`), and the chevron's `aria-controls` points at it. A virtual
  list gives each rendered row `aria-setsize` and `aria-posinset`.
  `MultiSelect`'s listbox is `aria-multiselectable`.

### Keyboard

| Key | Select | Combobox | MultiSelect | SegmentedControl |
| --- | --- | --- | --- | --- |
| Typing | type-ahead on labels (Radix) | filters and opens | filters and opens | — |
| ArrowDown / ArrowUp | open, then move | open, then move (no wrap) | open, then move (no wrap) | — |
| ArrowLeft / ArrowRight | — | caret | caret | move focus, looping |
| Home / End | first / last option | first / last while open; caret while closed | as Combobox | first / last item |
| Enter | select and close | select and close; never submits the form while open | toggle; list stays open; never submits while open | select the focused item |
| Space | select | types a space | types a space | select the focused item |
| Escape | close, no change | close, restore the selected label | close, clear the query | — |
| Tab | — (Radix keeps focus in the open list) | close, restore the label | close, clear the query | leaves the group |
| Backspace | — | edits the text | edits the text; in an empty input removes the last chip | — |

Focus alone never opens a Combobox or MultiSelect; a click on the input
does (and in a MultiSelect a press on the frame's padding or a chip's label
focuses the input and opens it too). Home and End jump in the open list but
edit the caret while it is closed: the spec's "Home and End jump while a
list is open" over the APG's caret-only reading.

### Hand-off to P1-T06

`Field` and `useFieldControl` come with P1-T06 (#2416, not merged). Until
then nothing here imports from it, and the seam is the props: `Select`,
`Combobox` and `MultiSelect` accept `id`, `aria-describedby`, `invalid` and
`disabled` on their trigger or input, matching `useFieldControl`'s
`FieldControlInput`, so they plug in without changes. `SegmentedControl`
takes `disabled`, `aria-label` and `aria-labelledby` only: it has no `id`,
`aria-describedby` or `invalid`, and `Field`'s `<label>` cannot name a
`radiogroup` in any case; label it with `aria-label` or point
`aria-labelledby` at a visible heading.

**Interim rule:** do not put these inside `Field` yet; its label would point
at its own control's id, not at the select. Name them with `aria-label` or
`aria-labelledby`, and show errors next to them yourself.

### SegmentedControl ruling

The design has no segmented-control frame. `SegmentedControl` takes the
shadcn tab-list treatment on the v1 tokens: a `muted` track with a 2px
inset, and the selected item as a `background` pill with `shadow-sm`.

## Select

```tsx
<Select aria-label="Mode" options={modes} value={mode} onValueChange={setMode}
  placeholder="Select a mode" />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `options` | `readonly SelectOption[]` | required | every one is rendered |
| `value` / `defaultValue` / `onValueChange` | `string` / `(value: string) => void` | — | controlled or not |
| `placeholder` | `string` | — | shown with no value |
| `name`, `required` | `string`, `boolean` | — | reach the hidden native select Radix renders inside a `<form>` |
| `disabled`, `invalid` | `boolean` | `false` | `invalid` sets `aria-invalid` and `data-invalid` |
| `id`, `aria-label`, `aria-labelledby`, `aria-describedby` | `string` | — | on the trigger |
| `className` | `string` | — | the trigger |

- A `value` or `defaultValue` that matches no option shows the placeholder:
  the wrapper maps it to `""`, since this Radix version would otherwise
  render a blank trigger.
- An option with `value: ""` makes Radix throw; `""` is Radix's "no value".
- No `loading` prop: a list you have to load belongs in a `Combobox`. An
  empty `options` shows a "No options" row.
- The trigger shows the selected option's `leading` and label, never its
  description.

## Combobox

```tsx
<Combobox aria-label="Model" options={models} value={model} onValueChange={setModel} />
<Combobox aria-label="Connector" loadOptions={searchConnectors} value={id}
  selectedOption={savedConnector} onValueChange={(value, option) => …} />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `options` | `readonly SelectOption[]` | `[]` | filtered on the client |
| `loadOptions` | `LoadOptions` = `(query: string, signal: AbortSignal) => Promise<readonly SelectOption[]>` | — | server search; `options` are ignored |
| `value` / `defaultValue` | `string \| null` | `null` | controlled or not |
| `onValueChange` | `(value: string \| null, option: SelectOption \| null) => void` | — | `null` when cleared |
| `selectedOption` | `SelectOption \| null` | — | names a preset `value` before the first load |
| `placeholder`, `emptyText` | `string` | — | `emptyText` replaces "No options" / "No matches" |
| `name` | `string` | — | a hidden input with the value, only while enabled |
| `disabled`, `invalid` | `boolean` | `false` | |
| `id`, `aria-label`, `aria-labelledby`, `aria-describedby` | `string` | — | on the input |
| `className` | `string` | — | the frame |

- While closed the input shows the selected label (and its `leading`),
  selected when the input takes focus or is clicked, so typing replaces it
  with the query. Enter or a click selects and closes; Escape, Tab and
  leaving the field close and restore the selected label.
- The chevron button ("Show options") toggles the list and keeps focus in
  the input; it is out of the tab order. The Clear button (shown with a
  value, while enabled) sets `null`.
- `loadOptions`: the first load after opening runs at once, later queries
  wait 250 ms. Each load aborts the one before through `signal`, a response
  for a query that is no longer current is dropped, and a "Loading…" row
  (with `aria-busy` on the listbox) or a "Could not load options" row shows
  the state. "Loading…" shows from the moment the list opens, and closing
  drops the loaded options, so a reopened list never flashes stale options
  or "No options". In async mode the client filters nothing: the loader's
  result is the list. Pass a stable or inline function, either works (it is
  read from a ref).
- Every option seen is remembered by value, so the selected label survives
  a filter or a server response that no longer holds it.

## MultiSelect

```tsx
<MultiSelect aria-label="Tags" options={tags} value={selected} onValueChange={setSelected}
  placeholder="Add tags" />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `options`, `loadOptions`, `placeholder`, `emptyText` | as Combobox | | the placeholder shows only with no chips |
| `value` / `defaultValue` | `readonly string[]` | `[]` | chip order; duplicates in a controlled `value` collapse |
| `onValueChange` | `(values: readonly string[]) => void` | — | |
| `selectedOptions` | `readonly SelectOption[]` | — | names preset values before the first load |
| `name` | `string` | — | one hidden input per value, only while enabled |
| `disabled`, `invalid`, `id`, `aria-label`, `aria-labelledby`, `aria-describedby`, `className` | as Combobox | | |

- Enter or a click toggles an option and keeps the list open, with the
  query cleared and the toggled option still active; choosing a selected
  option again removes it.
- Chips (`Chip`, 20 tall, `muted`) each have a remove button named
  "Remove {label}". The remove buttons are out of the tab order (one tab stop
  for the field, not one per chip): from the keyboard, Backspace in an empty
  input removes the last chip, and the open list toggles any chosen option
  off with Enter.

## SegmentedControl

```tsx
<SegmentedControl aria-label="Layout" value={layout} onValueChange={setLayout}
  options={[{ value: "split", label: "Split" }, { value: "unified", label: "Unified" }]} />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `options` | `readonly SegmentedOption[]` (`{ value, label, icon?, disabled? }`) | required | 2 to 5; any other count throws during render |
| `value` / `defaultValue` | `string` | the first enabled option | |
| `onValueChange` | `(value: string) => void` | — | only with a new, non-empty value |
| `disabled` | `boolean` | `false` | disables every item |
| `aria-label`, `aria-labelledby` | `string` | — | names the group |
| `className` | `string` | — | the group |

- Exactly one item is always selected; clicking the selected item keeps it.
- Radix ToggleGroup `type="single"` renders a `radiogroup` of `radio` items
  with `aria-checked`. Activation is manual: the arrows (Left/Right, looping,
  skipping disabled items) and Home/End move focus only, and Space or Enter
  selects. A native radio group selects as focus moves; this one does not.
- `label` is always shown and is the item's name; `icon` is a decorative
  lucide icon before it, sized 16.
- Caller contract: `value` must match an enabled option; `defaultValue`
  falls back to the first enabled one.

## Chip

`<Chip label="Invoices" onRemove={…} />`. `onRemove` adds the remove button;
`removeFocusable={false}` takes it out of the tab order (as MultiSelect
does); `disabled` disables it.

## Gallery and tests

`select.gallery.tsx` lists every closed state (each entry is static:
controlled values, no handlers, an `aria-label` on every control). Until the
component gallery (P1-T01) lands, `markup.test.tsx` renders each entry,
snapshots its markup in `__snapshots__/markup.md` and runs axe on it. Open
lists are not gallery entries: Radix portals them out of the rendered
container. `Listbox.test.tsx` and the component tests cover them, including
axe on the open state.

- Virtual lists need a laid-out scroll element: call `stubLayout()` from
  `@v1/test` (the 1,000-option tests in `Combobox.test.tsx` and
  `Listbox.test.tsx` do).
- Radix Select needed no DOM stubs under happy-dom 20, which has
  `scrollIntoView`, `hasPointerCapture`, `PointerEvent` and `ResizeObserver`.
