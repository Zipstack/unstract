import type { ReactNode } from "react";

/**
 * Any row object: an `interface`, an API response type with fields the chart
 * never reads, or a plain object. Only the keys a chart reads are constrained
 * (see `CategoryKey` and `NumericKey`).
 */
export type ChartDatum = object;

/** Keys of `Row` holding a category: a string or a number. */
export type CategoryKey<Row> = {
  [K in keyof Row]-?: Row[K] extends string | number ? K : never;
}[keyof Row] &
  string;

/**
 * Keys of `Row` holding a series value: a number, or null / undefined for a
 * gap. A numeric string ("12.5", as a DRF Decimal serialises) is rejected
 * here: parse it before charting, or Recharts would draw it while the
 * tooltip, table and summary treat it as a gap.
 */
export type NumericKey<Row> = {
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
  /** The field of each row that holds this series' value. */
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
 * never as a Recharts ReferenceLine or ReferenceDot: see `markers.ts`. A
 * marker on a series not in `series`, on a row outside `data` or on a gap is
 * neither drawn nor read out in the summary.
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
   * Default `ready`. Data with no rows shows the empty state too. There is no
   * error state: on a failed request render the page's `InlineAlert` (with
   * `onRetry`) instead of the chart, so a failure never reads as "no data".
   */
  state?: ChartState;
  /** Replaces the default empty message, e.g. with a page's EmptyState. */
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
