# Toggles

The one way v1 shows a checkbox, a switch, a radio group and a slider
(P1-T05, UN-4300). Import everything from `@v1/components/ui/toggles`:

```tsx
import {
  Checkbox,
  Radio,
  RadioGroup,
  Slider,
  Switch,
} from "@v1/components/ui/toggles";
```

| Component | Use it for | Size |
| --- | --- | --- |
| `Checkbox` | An option that is on or off and takes effect on save; "select all" (mixed) | 16 × 16 box |
| `Switch` | A setting that takes effect at once | 20 × 36, 16 thumb |
| `RadioGroup` + `Radio` | One choice from a few options, all visible | 14 radio |
| `Slider` | A number, or a range of two, within known bounds | 6 track, 16 thumb |

## Rules

- **Sizes come from the dev-spec board (§ 5).** Checkbox `ui:size-4`, radio
  `ui:size-3.5`, switch `ui:h-5 ui:w-9` with a `ui:size-4` thumb, slider
  track `ui:h-1.5` and thumb `ui:size-4`. Do not resize them with classes;
  `className` sets the outermost element (the row of a `Checkbox`, `Switch`
  or `Radio`; the whole field of a `RadioGroup` or `Slider`), never the
  control. Each control sits in a 20px box, the label's line height, so it
  centres on the label's first line.
- **One focus treatment.** Every focusable part uses
  `ui:focus-visible:focus-ring`. Disabled follows board § 6: opacity .5 and
  no pointer events, on the control and its label (a disabled `RadioGroup`
  dims its heading and every item label too).
- **Mixed is controlled only.** Pass `checked="indeterminate"`; the box then
  shows a minus. `defaultChecked` is `boolean` here on purpose: the icon is
  chosen from `checked`, so an uncontrolled mixed start would show a tick
  while reporting mixed. The icon is chosen in JS, never hidden with CSS.
- **Labels and descriptions.** Pass `label` and `description` rather than
  placing text beside a control: the label is tied by `htmlFor`, the
  description by `aria-describedby`, and both use the v1 type roles. A
  control with no visible label needs `aria-label`. A `RadioGroup` needs a
  name: `label` (used as `aria-labelledby`) or `aria-label`. Every slider
  thumb needs a name: see `Slider` below. A `label` or `description` of
  `false`, `""`, `null` or `undefined` counts as absent.
- **The checkbox icon is the Indicator itself.** v0's global rule forces any
  `svg.lucide` whose parent is a `span`, `p`, `label`, `li`, `a`, `td` or
  `th` to `1em` (see the v1 README, Styling), and it beats `ui:size-*`. So
  the Radix `Indicator` renders `asChild` onto the lucide svg, whose parent
  is then the `button`. Never wrap a lucide icon in a `span` in this folder.
- **The row is private.** Label and description are drawn by `ControlRow`
  with the same text classes as `Label` and `HelperText` in the P1-T03 form
  components. Do not import `ControlRow`; it is not exported.
- **Not inside `Field` yet (P1-T03 / P1-T06).** `Field` is a vertical grid
  whose required `label` renders above the control as `<Label htmlFor>`
  (an 18px line). A `<label for>` cannot name a `role="radiogroup"`, so a
  `RadioGroup` never goes inside `Field`. The toggles' `id`,
  `aria-describedby` and `disabled` already line up with `useFieldControl`'s
  `FieldControlInput`; `invalid` would be additive. In P1-T06 the toggles
  read `useFieldControl` for id, description, invalid and disabled;
  `ControlRow` keeps its label-beside layout and may reuse `Label` and
  `HelperText`; `Field` wraps only single-control cases (the slider, with
  Field's id sent to the thumb). Until P1-T06, do not put a toggle inside
  `Field`: Field's label would point at its own generated id and name
  nothing.

## Checkbox

```tsx
<Checkbox label="Include page numbers" checked={on} onCheckedChange={(v) => setOn(v === true)} />
<Checkbox label="Select all" checked={some ? "indeterminate" : all} onCheckedChange={toggleAll} />
<Checkbox aria-label="Select row" checked={selected} onCheckedChange={select} />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `checked` | `boolean \| "indeterminate"` | — | controlled; `"indeterminate"` shows a minus |
| `defaultChecked` | `boolean` | — | uncontrolled start; mixed is controlled only |
| `onCheckedChange` | `(checked: boolean \| "indeterminate") => void` | — | |
| `label` | `ReactNode` | — | beside the box, tied by `htmlFor` |
| `description` | `ReactNode` | — | under the label, tied by `aria-describedby` |
| `disabled` | `boolean` | — | dims the label too |
| `id` | `string` | generated | the button's id |
| `className` | `string` | — | the row, not the box |

Other Radix `Checkbox.Root` props (`name`, `value`, `required`,
`aria-label`, `aria-describedby`…) pass through to the button; a caller's
`aria-describedby` is kept alongside the description's.

## Switch

```tsx
<Switch label="Enable webhook" checked={enabled} onCheckedChange={setEnabled} />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `checked` / `defaultChecked` | `boolean` | — | controlled or not |
| `onCheckedChange` | `(checked: boolean) => void` | — | |
| `label`, `description`, `disabled`, `id`, `className` | | | as Checkbox |

Other Radix `Switch.Root` props pass through to the button.

## RadioGroup and Radio

```tsx
<RadioGroup label="Extraction mode" value={mode} onValueChange={setMode}>
  <Radio value="native" label="Native text" />
  <Radio value="form" label="Form" />
  <Radio value="high" label="High quality" disabled />
</RadioGroup>
<RadioGroup aria-label="Output" orientation="horizontal" defaultValue="json">…</RadioGroup>
```

`RadioGroup`:

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `value` / `defaultValue` | `string` | — | controlled or not |
| `onValueChange` | `(value: string) => void` | — | |
| `label` | `ReactNode` | — | heading above the items, used as `aria-labelledby`; without it pass `aria-label` |
| `description` | `ReactNode` | — | under the heading, tied by `aria-describedby` |
| `orientation` | `"vertical" \| "horizontal"` | — (a column) | horizontal lays the items in a wrapping row |
| `disabled` | `boolean` | `false` | disables every item and dims the heading and labels |
| `className` | `string` | — | the whole field (heading, description and items), not the item list |

`Radio`:

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `value` | `string` | required | |
| `label`, `description`, `disabled`, `id`, `className` | | | as Checkbox |

Arrow keys move the selection and focus together and skip disabled items.
Other Radix `RadioGroup.Root` and `RadioGroup.Item` props (`name`,
`required`, `loop`…) pass through.

## Slider

```tsx
<Slider label="Temperature" min={0} max={1} step={0.1} value={[t]}
  onValueChange={([v]) => setT(v)} formatValue={(v) => v.toFixed(2)} showValue />
<Slider label="Pages" min={1} max={pageCount} value={range} onValueChange={setRange}
  thumbLabels={["First page", "Last page"]} showValue />
```

| Prop | Type | Default | |
| --- | --- | --- | --- |
| `value` / `defaultValue` | `number[]` | `[min]` | one thumb per value; controlled or not |
| `onValueChange` | `(value: number[]) => void` | — | on every move |
| `onValueCommit` | `(value: number[]) => void` | — | on release, from Radix |
| `min`, `max`, `step` | `number` | `0`, `100`, `1` | |
| `label` | `ReactNode` | — | above the track, used as `aria-labelledby` |
| `description` | `ReactNode` | — | under the label, tied by `aria-describedby` |
| `thumbLabels` | `readonly string[]` | — | a name per thumb, in order; its length must match the number of values |
| `formatValue` | `(value: number) => string` | `String` | each thumb's `aria-valuetext`, and the shown value |
| `showValue` | `boolean` | `false` | the formatted value(s) at the end of the label line, a range as "3 – 12" |
| `disabled` | `boolean` | — | dims the label and the track; each thumb gets `aria-disabled` |
| `className` | `string` | — | the whole field, so `ui:max-w-xs` narrows the label line and the track together |

A single thumb is named by `thumbLabels[0]`, else a string `label`, else the
root's `aria-label`; a single thumb with a non-string `label` (say
`<em>Temperature</em>`) and no `aria-label` gets `aria-labelledby` pointing
at the label. A range keeps Radix's "Minimum" / "Maximum" names unless
`thumbLabels` is given, so name the thumbs for anything less generic.
The root is a `group` named by the label and described by the description,
and every thumb carries the same `aria-describedby`, since the thumbs are
what assistive tech focuses. Arrows move by `step`, PageUp/PageDown by ten
steps, Home and End jump to `min` and `max`. Only horizontal is supported:
`orientation` is not a prop.

## Gallery and tests

`toggles.gallery.tsx` lists every variant and state, each controlled and
static. It is not exported from `index.ts`; the component gallery (P1-T01)
imports `./toggles.gallery` directly. Until the component gallery (P1-T01) lands, `markup.test.tsx` renders
each entry, snapshots its markup in `__snapshots__/markup.md` and runs axe on
it. Behaviour (keyboard, mixed state, disabled dimming, thumb names) is in
each component's `*.test.tsx`, rendered with `renderV1` from `@v1/test`.
