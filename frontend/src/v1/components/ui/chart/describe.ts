import type { ChartDatum, ChartSeries } from "./types";

/** What the summary calls each chart. */
export type ChartKind = "line" | "area" | "bar" | "stacked-bar" | "sparkline";

const KIND_NAMES: Readonly<Record<ChartKind, string>> = {
  line: "Line chart",
  area: "Area chart",
  bar: "Bar chart",
  "stacked-bar": "Stacked bar chart",
  sparkline: "Sparkline",
};

/**
 * The default value and axis formatters for a locale; leave it out for the
 * viewer's own. Tests pass a fixed one, so their expectations do not depend
 * on the machine they run on.
 */
export function numberFormats(locale?: string): Readonly<{
  value: (value: number) => string;
  axis: (value: number) => string;
}> {
  const grouped = new Intl.NumberFormat(locale);
  const compact = new Intl.NumberFormat(locale, {
    notation: "compact",
    maximumFractionDigits: 1,
  });
  return {
    value: (value) => grouped.format(value),
    axis: (value) => compact.format(value),
  };
}

const VIEWER = numberFormats();

/** Grouped, in the viewer's locale: 2,981. */
export const formatValue = VIEWER.value;

/** Compact, in the viewer's locale, for axis ticks: 3K, 2.3K. */
export const formatAxisValue = VIEWER.axis;

export function formatCategory(value: string | number): string {
  return String(value);
}

/** The row's value for `key` as a finite number, or null for a gap. */
export function numberAt(row: ChartDatum, key: string): number | null {
  const value: unknown = (row as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * True when some series has a value on some row. A gap is what `numberAt`
 * reads as one (null, missing, not a finite number), the same rule as the
 * tooltip, table, summary and markers, so a chart whose series are all gaps
 * (a period with no activity, bucketed by day) shows the empty state, not a
 * blank plot. An unparsed numeric string is a gap too: parse it first.
 * Only the series' own keys are read.
 */
export function hasValues(
  data: readonly ChartDatum[],
  series: readonly Readonly<{ key: string }>[],
): boolean {
  return data.some((row) => series.some((s) => numberAt(row, s.key) !== null));
}

/**
 * A console warning for each series holding something that is present but
 * not a number (an unparsed DRF Decimal string): the chart reads it as a
 * gap, so a payload the page forgot to parse would otherwise read as "no
 * data" with nothing to say why.
 */
export function unparsedWarnings(
  data: readonly ChartDatum[],
  series: readonly Readonly<{ key: string }>[],
): string[] {
  return series
    .filter((s) =>
      data.some((row) => {
        const value: unknown = (row as Record<string, unknown>)[s.key];
        return (
          value !== null && value !== undefined && typeof value !== "number"
        );
      }),
    )
    .map(
      (s) =>
        `Chart series "${s.key}" has values that are not numbers; the chart reads them as gaps. Parse numeric strings before passing them.`,
    );
}

export type Formatters = Readonly<{
  value: (value: number) => string;
  x: (value: string | number) => string;
}>;

function categoryAt(
  row: ChartDatum | undefined,
  xKey: string,
  fmt: Formatters,
): string {
  const value: unknown =
    row === undefined ? undefined : (row as Record<string, unknown>)[xKey];
  return typeof value === "string" || typeof value === "number"
    ? fmt.x(value)
    : "";
}

/**
 * The fallback text alternative: the chart kind, the category range, and each
 * series' highest and lowest point, then the labels of the markers that are
 * drawn (`keptLabels`). Pages with a better sentence pass `summary`.
 */
export function describeChart<Row extends ChartDatum>(
  input: Readonly<{
    kind: ChartKind;
    title: string;
    data: readonly Row[];
    xKey: string;
    series: readonly ChartSeries<Row>[];
    markerLabels?: readonly string[];
    fmt: Formatters;
  }>,
): string {
  const { kind, title, data, xKey, series, markerLabels = [], fmt } = input;
  const first = categoryAt(data[0], xKey, fmt);
  const last = categoryAt(data[data.length - 1], xKey, fmt);
  const range =
    data.length === 1
      ? `1 point, ${first}`
      : `${data.length} points from ${first} to ${last}`;
  const parts = [`${title}. ${KIND_NAMES[kind]}, ${range}.`];
  for (const s of series) {
    const format = s.format ?? fmt.value;
    let max: { value: number; at: string } | null = null;
    let min: { value: number; at: string } | null = null;
    for (const row of data) {
      const value = numberAt(row, s.key);
      if (value === null) {
        continue;
      }
      const at = categoryAt(row, xKey, fmt);
      if (max === null || value > max.value) {
        max = { value, at };
      }
      if (min === null || value < min.value) {
        min = { value, at };
      }
    }
    parts.push(
      max === null || min === null
        ? `${s.label}: no values.`
        : `${s.label}: highest ${format(max.value)} at ${max.at}, lowest ${format(min.value)} at ${min.at}.`,
    );
  }
  if (markerLabels.length > 0) {
    parts.push(`Marked: ${markerLabels.join("; ")}.`);
  }
  return parts.join(" ");
}

/** The data table's cells: one row per datum, the category then each series. */
export function tableRows<Row extends ChartDatum>(
  data: readonly Row[],
  xKey: string,
  series: readonly ChartSeries<Row>[],
  fmt: Formatters,
): string[][] {
  return data.map((row) => [
    categoryAt(row, xKey, fmt),
    ...series.map((s) => {
      const value = numberAt(row, s.key);
      return value === null ? "–" : (s.format ?? fmt.value)(value);
    }),
  ]);
}
