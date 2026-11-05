# Charts

Five charts on Recharts, imported from `@v1/components/ui/chart`:
`LineChart`, `AreaChart`, `BarChart`, `StackedBarChart` and `Sparkline`. They
share one props model, take their colours from tokens, and each has loading
and empty states and a text alternative; the four axis charts also have a
tooltip and a legend (the sparkline's tooltip is opt-in, and it has no
legend). Never
import `recharts` in a page for a chart these cover; add what you need here
so every chart keeps the same colours, states and accessibility.

## Example

```tsx
import { LineChart } from "@v1/components/ui/chart";

<LineChart
  title="Throughput and failures"          // accessible name; not drawn
  data={daily}                             // [{ day: "10 Aug", pages: 2981, failed: 600 }, …]
  xKey="day"
  xLabel="Day"                             // header of the data table's first column
  series={[
    { key: "pages", label: "Pages processed", tone: "primary" },
    { key: "failed", label: "Failed pages", tone: "destructive" },
  ]}
  markers={[{ index: peakIndex, series: "pages", label: "10 Aug · 2,981 pages" }]}
  state={query.isPending ? "loading" : "ready"}
  emptySlot={<EmptyState … />}
/>
```

A chart has no error state. When the request fails, render the page's
`InlineAlert` with `onRetry` **instead of** the chart, so a failure never reads
as "No data for this period":

```tsx
{query.isError ? (
  <InlineAlert kind="error" title="Could not load throughput" onRetry={query.refetch} />
) : (
  <LineChart … />
)}
```

```tsx
import { StackedBarChart } from "@v1/components/ui/chart";

// LLMWhisperer pages by mode: no tones, so the series take the ramp in order,
// lightest first. Order them cheapest to most expensive.
<StackedBarChart
  title="Pages by mode"
  data={days}
  xKey="day"
  legend="top"
  series={MODES.map((m) => ({ key: m.id, label: m.name }))}
/>
```

```tsx
import { Sparkline } from "@v1/components/ui/chart";

<Sparkline
  title="Pages processed, last 30 days"
  data={daily}
  xKey="day"
  series={[{ key: "pages", label: "Pages", tone: "primary" }]}
/>
```

## Props

Every chart:

| Prop | Type | Default | Notes |
| --- | --- | --- | --- |
| `data` | `readonly Row[]` | required | One row per category. `Row` is any object type, an `interface` or an API type with extra fields included, and is inferred from here: type an inline empty literal (`data={[] as Row[]}`), or it infers `never` and rejects every key. |
| `xKey` | key of `Row` holding a string or number | required | The category field. Categories may repeat. |
| `series` | `ChartSeries[]` | required | `{ key, label, tone?, axis?, format? }`, drawn in this order. `key` must name a field typed `number \| null \| undefined`; null or undefined is a gap. Parse numeric strings (a DRF Decimal) first. |
| `title` | `string` | required | The plot's accessible name and the table caption. The card shows the visible heading. |
| `summary` | `string` | generated | The sentence screen readers hear. Pass one when the page knows the story ("10 Aug alone carries 49% of the month's pages"). |
| `xLabel` | `string` | `"Category"` | First column header of the data table. |
| `state` | `"ready" \| "loading" \| "empty"` | `"ready"` | `ready` with no rows shows the empty state. |
| `emptySlot` | `ReactNode` | — | Replaces the empty message, e.g. with the page's EmptyState. |
| `emptyMessage` | `string` | `"No data for this period"` | |
| `height` | `number` | 240 (sparkline 40) | Plot height in pixels. |
| `width` | `number` | fills the container | Fixed width in pixels. |
| `valueFormat` | `(n) => string` | `2,981`, viewer's locale | Tooltip, summary and table. A series' `format` overrides it. |
| `xFormat` | `(x) => string` | `String` | X ticks, tooltip heading, summary and table. |
| `className` | `string` | — | On the outer element. |

`LineChart`, `AreaChart`, `BarChart`, `StackedBarChart` also take:

| Prop | Type | Default | Notes |
| --- | --- | --- | --- |
| `markers` | `ChartMarker[]` | `[]` | `{ index, series, label }`: a labelled dot on row `index` of `series`. A marker on a series not charted, a row outside `data`, a gap, or a point an earlier marker already labels is dropped, from the plot and the summary alike, with a console warning saying why (only once the chart shows data, so markers computed ahead of loading rows do not warn). |
| `legend` | `"top" \| "bottom" \| "none"` | `"bottom"` | |
| `axisFormat` | `(n) => string` | `2.3K`, viewer's locale | Left Y axis ticks. |
| `rightAxisFormat` | `(n) => string` | `axisFormat` | Right Y axis ticks. |
| `grid` | `boolean` | `true` | Horizontal grid lines. |

`Sparkline` has no axes, grid, legend or markers, and takes `tooltip`
(default `false`).

`series` and `markers` may be inline literals: the chart keys its work on
what they say, not on their identity. Rows typed with a string index
signature (`Record<string, number>`, pivoted rows with one field per dynamic
series) accept any key whose field could hold a number, since the type
cannot check them per field (`Record<string, string>` accepts none;
`Record<string, unknown>` accepts any). Field
names starting with `__marker` are reserved for markers: a chart with such
a series key warns (in any state) and draws no markers. Wrappers
that take a key generically can type it with the exported `NumericKey<Row>`
and `CategoryKey<Row>`.

A series with `axis: "right"` reads against a second Y axis, drawn only when
some series asks for it. In a `StackedBarChart`, right-axis series form their
own stack.

## Colour

- Series without a `tone` take the ordinal ramp `--chart-1` … `--chart-5` in
  order (the first untoned series is `--chart-1` whatever comes before it).
  The ramp is one hue (blue), lightest (`--chart-1`) to darkest (`--chart-5`)
  in every mode, so a category keeps its shade across modes. Use it for
  ordered categories: modes, tiers, buckets.
- After five untoned series the ramp repeats. Do not go past five: a single-hue
  ramp cannot separate more. Group the tail into "Other", or use tones.
- A `tone` takes a series out of the ramp for meaning: `primary`,
  `destructive` (failures), `success`, `warning`, `muted`
  (`muted-foreground`).
- Every ramp step and tone reaches 3:1 against `card` in every mode (WCAG
  1.4.11), enforced by `palette.test.ts`. Change a value in
  `styles/tokens.json` and that test tells you if it got too light.
- Stacked segments are split by a 1px `card`-coloured stroke, so neighbouring
  steps read apart.

## Markers: drawn from the series, never a reference line

Mark a point (a peak day, a spike) with `markers`. On a line or area they
become a dot-only series aligned to the row; on a bar they are drawn from the
bar itself, so the dot sits over its own bar in a group and on top of its own
segment in a stack. Do not reach for Recharts' `ReferenceLine` or
`ReferenceDot` on a categorical axis: they address a point by its category
label, and when a label repeats ("Mon" across two weeks) recharts 3.7.0
silently draws nothing. A marker addresses a row by index, so it always
lands. `charts.test.tsx` asserts no reference element is rendered.

## Text alternative

Every chart renders, beside the plot:

- the `summary` (or a generated sentence: chart kind, category range, each
  series' highest and lowest point, and the markers), which the plot names
  through `aria-describedby`;
- a visually hidden table of every value, captioned with `title`.

The plot itself is a focusable `role="application"` with `aria-label={title}`:
Tab to it, then the arrow keys move the tooltip from category to category. A
sparkline without a tooltip is a static `role="img"` outside the tab order.

## States

- `loading`: the shared `Skeleton` with one `SkeletonBlock` at the chart's
  height, announced as "Loading {title}". Never a spinner.
- `empty`: a centred message at the chart's height, or `emptySlot`.
- error: not a chart state. Render `InlineAlert` with `onRetry` in its place.

A point with no defined neighbour (a single row, or a value between two gaps)
is drawn as a dot, since a line through one point paints nothing.

## Testing a page that uses a chart

Pass `width` (and `height`), or call `installResizeObserver()` from
`@v1/test` and `resize` the container. A hover needs
`getBoundingClientRect`, `offsetWidth` and `offsetHeight` stubbed on
`HTMLElement.prototype` and a `waitFor`, because Recharts reads the pointer on
the next animation frame (see `stubLayout` in `charts.test.tsx`). Default
number formats follow the machine's locale, so pass
`valueFormat={numberFormats("en-US").value}` (and `axisFormat`) where a test
asserts formatted numbers. The arrow
keys need no stubs. Recharts draws SVG; there is no canvas.
