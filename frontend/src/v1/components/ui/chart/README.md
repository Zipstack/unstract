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
  emptySlot={<YourEmptyState … />}        // must fit `height`
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
| `series` | `ChartSeries[]` | required | `{ key, label, tone?, axis?, format? }`, drawn in this order. `key` must name a field typed `number \| null \| undefined`; null, undefined or anything not a finite number is a gap to the tooltip, table, summary, markers and empty state. Parse numeric strings (a DRF Decimal) first: an unparsed one is a gap and logs a console warning naming the series (if every value is one, the chart shows its empty state), though Recharts may still draw it. |
| `title` | `string` | required | The plot's accessible name and the table caption. The card shows the visible heading. |
| `summary` | `string` | generated | The sentence screen readers hear. Pass one when the page knows the story ("10 Aug alone carries 49% of the month's pages"). |
| `xLabel` | `string` | `"Category"` | First column header of the data table. |
| `state` | `"ready" \| "loading" \| "empty"` | `"ready"` | `ready` with no rows, or only gaps, shows the empty state. |
| `emptySlot` | `ReactNode` | — | Replaces the empty message. It is centred in a box of the chart's `height` (40 on a sparkline) and the box does not grow, so the slot must fit; it replaces the screen-reader title prefix too, so name the chart in it. |
| `emptyMessage` | `string` | `"No data for this period"` | |
| `height` | `number` | 240 (sparkline 40) | Plot height in pixels. |
| `width` | `number` | fills the container | Fixed width in pixels. |
| `valueFormat` | `(n) => string` | `2,981`, viewer's locale | Tooltip, summary and table. A series' `format` overrides it. |
| `xFormat` | `(x) => string` | `String` | X ticks, tooltip heading, summary and table. |
| `className` | `string` | — | On the outer element. |

`LineChart`, `AreaChart`, `BarChart`, `StackedBarChart` also take:

| Prop | Type | Default | Notes |
| --- | --- | --- | --- |
| `markers` | `ChartMarker[]` | `[]` | `{ index, series, label }`: a labelled dot on row `index` of `series`. A marker on a series not charted, a row outside `data`, a gap, or a point an earlier marker already labels is dropped (and every marker, when a series key is reserved; see below), from the plot and the summary alike, with a console warning saying why (only when the chart shows data, so markers computed ahead of loading rows do not warn). |
| `legend` | `"top" \| "bottom" \| "none"` | `"bottom"` | |
| `axisFormat` | `(n) => string` | `2.3K`, viewer's locale | Left Y axis ticks. |
| `rightAxisFormat` | `(n) => string` | `axisFormat` | Right Y axis ticks. |
| `grid` | `boolean` | `true` | Horizontal grid lines. |

`Sparkline` has no axes, grid, legend or markers, and takes `tooltip`
(default `false`).

`series` and `markers` may be inline literals: the chart keys its work on
what they say, not on their identity. `data` is different: pass a stable
array (the query result, or a `useMemo` over it). A new array on every
render makes Recharts reset its data store (and the axis charts recompute
their rows). Rows typed with a string index
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

- A single series takes `primary`, or the tone for its meaning
  (`destructive` for failures).
- Series that are not stacked (several lines, overlaid areas, grouped bars):
  give each a `tone` for what it means, as the Document Studio dashboard
  design does for "Throughput and failures" (`primary` for pages processed,
  `destructive` for failed pages). The tones are `primary`, `destructive`
  (failures), `success`, `warning` and `muted` (`muted-foreground`). A series
  left untoned takes the next ramp step, with no warning.
- The segments of a stack, ordered buckets such as modes or tiers, take the
  ordinal ramp `--chart-1` … `--chart-5`: leave them untoned and they take
  it in order. The ramp is the LLMWhisperer design's mode colours
  (`--mode-native-text` … `--mode-table`), lightest to darkest, per mode as
  designed; its "Pages by mode" stack is the model. A 1px `card`-coloured
  stroke splits the segments.
- Keep a chart to five untoned series, counting both stacks together when
  some series sit on the right axis: the ramp has five steps and the sixth
  untoned series repeats `--chart-1`, with no warning. Group the tail into
  "Other".
- Use tones or the ramp on a chart, not both. Nothing checks colours against
  each other or against the background.

## Known gaps

Designed charts these components do not cover yet. Each is for its page's
owner to settle, not part of P1-T17.

- **Categorical donuts** (Human Review H29, changes by field and by user): no
  Pie or Donut chart here, and the design's segment colours are not tokens.
- **A free-choice comparison series** (Document Studio D12, "Compare on this
  chart"; P4-T04): a series picked from nine metrics has no meaning to give
  it a tone, and no colour is designed for it.
- **KPI sparklines whose colour is not a meaning** (Document Studio D01):
  "LLM spend" is drawn in `warning` and "Documents processed" in a blue that
  is not a token. The single-series rule above gives them `primary` until
  the design names a token.

## Markers: drawn from the series, never a reference line

Mark a point (a peak day, a spike) with `markers`. On a line or area they
become a dot-only series aligned to the row; on a bar they are drawn from the
bar itself, so the dot sits on its own bar's tip in a group and on its own
segment's tip in a stack (the top, or the bottom below zero, where the label
reads under the tip, or beside the dot at the plot's bottom edge). Do not reach for Recharts' `ReferenceLine` or
`ReferenceDot` on a categorical axis: they address a point by its category
label, and when a label repeats ("Mon" across two weeks) recharts 3.7.0
silently draws nothing. A marker addresses a row by index, so it always
lands. `charts.test.tsx` asserts no reference element is rendered.

## Text alternative

Every chart renders, beside the plot:

- the `summary` (or a generated sentence: chart kind, category range, each
  series' highest and lowest point, and the markers), which the plot names
  through `aria-describedby`;
- a visually hidden table of every value, captioned with `title`;
- a polite live region (`data-slot="chart-live"`) that reads out the active
  point as the tooltip moves ("no data" for a gap), and empties when it
  closes.

The plot itself is a focusable `role="application"` with `aria-label={title}`:
Tab to it, then the arrow keys move the tooltip from category to category. A
sparkline without a tooltip is a static `role="img"` outside the tab order.

## States

- `loading`: the shared `Skeleton` with one `SkeletonBlock` at the chart's
  height, announced as "Loading {title}". Never a spinner.
- `empty`: a centred message at the chart's height, or `emptySlot`, which must
  fit that height.
- Both keep the ready chart's footprint when `series` is known before the
  data: its legend is laid out, invisibly, in the same place, so a card does
  not jump when data arrives. Series built from the response (pivoted rows)
  are empty until it arrives, so nothing is reserved; pass the series you
  expect while loading if the card must not move.
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
