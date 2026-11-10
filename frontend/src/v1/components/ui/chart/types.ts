import type { ReactNode } from "react";

/**
 * Any row object: an `interface`, an API response type with fields the chart
 * never reads, or a plain object. Only the keys a chart reads are constrained
 * (see `CategoryKey` and `NumericKey`).
 */
export type ChartDatum = object;

/** The value type of `Row`'s string index signature, where it has one. */
type IndexValue<Row> = Row[string & keyof Row];

/**
 * Keys of `Row` holding a category: a string or a number. A row typed with a
 * string index signature (`Record<string, string | number>`, as pivoted rows
 * with one field per dynamic series are) cannot be checked per key, so there
 * any string is accepted when the index's value type includes a string or a
 * number, or is `unknown` / `any` (nothing is known either way), and none
 * otherwise (`Record<string, Date>`). An untyped `[]` infers `never`, whose
 * index is `never`, so it accepts no key.
 */
export type CategoryKey<Row> = string extends keyof Row
  ? unknown extends IndexValue<Row>
    ? string
    : [Extract<IndexValue<Row>, string | number>] extends [never]
      ? never
      : string
  : {
      [K in keyof Row]-?: Row[K] extends string | number ? K : never;
    }[keyof Row] &
      string;

/**
 * Keys of `Row` holding a series value: a number, or null / undefined for a
 * gap. A numeric string ("12.5", as a DRF Decimal serialises) is rejected
 * here: parse it before charting, or Recharts would draw it while the
 * tooltip, table and summary treat it as a gap. A row with a string index
 * signature accepts any string when the index's value type includes a number
 * (`Record<string, string | number>`, `Record<string, 0 | 1>`) or is
 * `unknown` / `any`, and none otherwise (`Record<string, string>`); `never`
 * accepts none.
 */
export type NumericKey<Row> = string extends keyof Row
  ? unknown extends IndexValue<Row>
    ? string
    : [Extract<IndexValue<Row>, number>] extends [never]
      ? never
      : string
  : {
      [K in keyof Row]-?: Row[K] extends number | null | undefined ? K : never;
    }[keyof Row] &
      string;

/**
 * A meaning-carrying colour that takes a series out of the ordinal ramp, e.g.
 * failed pages in `destructive`. Each maps to the semantic token of that name
 * (`muted` to `muted-foreground`).
 */
export type ChartTone =
  | "primary"
  | "destructive"
  | "success"
  | "warning"
  | "muted";

export type ChartSeries<Row extends ChartDatum> = Readonly<{
  /**
   * The field of each row that holds this series' value. Must not start with
   * `__marker`, which the chart reserves for markers (a chart with such a key
   * draws no markers, and warns). Checked at runtime rather than in this
   * type, so that `Row` inference from `data` stays simple.
   */
  key: NumericKey<Row>;
  /** Shown in the legend, the tooltip, the summary and the data table. */
  label: string;
  /** Leave out to take the next step of the ordinal ramp. */
  tone?: ChartTone;
  /** Which Y axis this series reads against. Default `left`. */
  axis?: "left" | "right";
  /** Formats this series' values in the tooltip, summary and table; overrides `valueFormat`. */
  format?: (value: number) => string;
}>;

/**
 * A highlighted point on a series (peak day, spike). Drawn from the series,
 * never as a Recharts ReferenceLine or ReferenceDot. A marker is drawn and
 * read out in the summary only when its series is charted, its index is an
 * integer row of `data`, the series has a value on that row, no earlier
 * marker labels that point, and no series key starts with `__marker`;
 * otherwise it is dropped, with a console warning when the chart shows data.
 */
export type ChartMarker<Row extends ChartDatum> = Readonly<{
  /** Row index in `data`, so repeated category labels stay unambiguous. */
  index: number;
  /** The series the marker sits on. */
  series: NumericKey<Row>;
  /** Drawn above the dot, and read out in the summary. */
  label: string;
}>;

export type ChartState = "ready" | "loading" | "empty";

/** Props every chart shares. */
export type BaseChartProps<Row extends ChartDatum> = Readonly<{
  /**
   * `Row` is inferred from here. An untyped empty literal (`data={[]}`)
   * infers `never`, which accepts no key, so type it: `data={[] as Row[]}`,
   * or pass the type argument (`<LineChart<Row> …>`).
   */
  data: readonly Row[];
  /** The field holding each row's category (a date, a mode). */
  xKey: CategoryKey<Row>;
  /** Names the category column of the data table, e.g. "Date". Default "Category". */
  xLabel?: string;
  series: readonly ChartSeries<Row>[];
  /**
   * The chart's accessible name, e.g. "Throughput and failures". Not drawn:
   * the card around the chart shows its own heading.
   */
  title: string;
  /** A sentence describing what the chart shows; generated from the data when left out. */
  summary?: string;
  /**
   * Default `ready`. Data with no rows, or whose every series value is a gap,
   * shows the empty state too. There is no
   * error state: on a failed request render the page's `InlineAlert` (with
   * `onRetry`) instead of the chart, so a failure never reads as "no data".
   */
  state?: ChartState;
  /**
   * Replaces the default empty message. It is centred in a box of `height`
   * that does not grow, so it must fit, and it replaces the screen-reader
   * title prefix, so it should name the chart.
   */
  emptySlot?: ReactNode;
  /** Default "No data for this period". */
  emptyMessage?: string;
  /** Plot height in pixels. */
  height?: number;
  /** Fixed width in pixels; leave out to fill the container. */
  width?: number;
  /** Formats values in the tooltip, summary and table. Default: grouped number (2,981). */
  valueFormat?: (value: number) => string;
  /** Formats categories on the X axis, the tooltip, summary and table. Default: `String`. */
  xFormat?: (value: string | number) => string;
  className?: string;
}>;

/** Props of the four charts with axes (all but the sparkline). */
export type CartesianChartProps<Row extends ChartDatum> = BaseChartProps<Row> &
  Readonly<{
    markers?: readonly ChartMarker<Row>[];
    /** Where the legend sits; `none` hides it. Default `bottom`. */
    legend?: "top" | "bottom" | "none";
    /** Formats left Y axis ticks. Default: compact number (2.3K). */
    axisFormat?: (value: number) => string;
    /** Formats right Y axis ticks (series with `axis: "right"`). Default: `axisFormat`. */
    rightAxisFormat?: (value: number) => string;
    /** Draws horizontal grid lines. Default true. */
    grid?: boolean;
  }>;
