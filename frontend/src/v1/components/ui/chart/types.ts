import type { ReactNode } from "react";

/** One row of chart data: the category (`xKey`) plus one number per series. */
export type ChartDatum = Readonly<
  Record<string, string | number | null | undefined>
>;

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
  key: keyof Row & string;
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
 * A highlighted point on a series (peak day, spike). Drawn as a dot-only
 * series, never as a Recharts ReferenceLine or ReferenceDot: see `markers.ts`.
 */
export type ChartMarker<Row extends ChartDatum> = Readonly<{
  /** Row index in `data`, so repeated category labels stay unambiguous. */
  index: number;
  /** The series the marker sits on. */
  series: keyof Row & string;
  /** Drawn above the dot, and read out in the summary. */
  label: string;
}>;

export type ChartState = "ready" | "loading" | "empty";

/** Props every chart shares. */
export type BaseChartProps<Row extends ChartDatum> = Readonly<{
  data: readonly Row[];
  /** The field holding each row's category (a date, a mode). */
  xKey: keyof Row & string;
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
  /** Default `ready`. Data with no rows shows the empty state too. */
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
    /** Formats Y axis ticks. Default: compact number (2.3K). */
    axisFormat?: (value: number) => string;
    /** Draws horizontal grid lines. Default true. */
    grid?: boolean;
  }>;
