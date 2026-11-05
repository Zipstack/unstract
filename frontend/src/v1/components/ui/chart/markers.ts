import { numberAt } from "./describe";
import type { ChartDatum, ChartMarker, ChartSeries } from "./types";

/*
 * Markers are drawn from the data, never with Recharts' ReferenceLine or
 * ReferenceDot. Those address a point by its category value, and on a
 * categorical axis that is the known defect: when a category label repeats
 * (the default `allowDuplicatedCategory`, e.g. "Mon" across two weeks or
 * "10 Aug" across two years) recharts 3.7.0 silently draws nothing, and even
 * when it draws, the marker cannot say which of two equal labels it means. A
 * marker here is indexed by row, so it always lands on the point it names:
 * on a line or area as a dot-only series aligned to the row, on a bar from
 * the bar itself (so it sits over its own bar in a group, and on top of its
 * own segment in a stack). `charts.test.tsx` asserts no reference element is
 * ever rendered.
 */

/** The dataKey of series `seriesIndex`'s marker values on a line or area chart. */
export function markerKey(seriesIndex: number): string {
  return `__marker_${seriesIndex}`;
}

/** Marker labels by row index, for each series that has at least one. */
export type MarkerLabels = ReadonlyMap<number, ReadonlyMap<number, string>>;

/**
 * The markers that will be drawn, by series index then row index. The one
 * rule for which markers count, used by the plot and the summary alike: the
 * series is charted, the index is an integer row of `data`, and the series
 * has a value on that row. Anything else is dropped, never drawn and never
 * read out, with a console warning naming the marker and why.
 */
export function keptMarkers<Row extends ChartDatum>(
  data: readonly Row[],
  series: readonly ChartSeries<Row>[],
  markers: readonly ChartMarker<Row>[],
): MarkerLabels {
  const kept = new Map<number, Map<number, string>>();
  for (const marker of markers) {
    const seriesIndex = series.findIndex((s) => s.key === marker.series);
    const reason =
      seriesIndex === -1
        ? "its series is not charted"
        : !Number.isInteger(marker.index) ||
            marker.index < 0 ||
            marker.index >= data.length
          ? `row ${marker.index} is not a row of data (${data.length} rows)`
          : numberAt(data[marker.index], marker.series) === null
            ? "the series has no value on that row"
            : null;
    if (reason !== null) {
      console.warn(`Chart marker "${marker.label}" not drawn: ${reason}.`);
      continue;
    }
    const forSeries = kept.get(seriesIndex) ?? new Map<number, string>();
    forSeries.set(marker.index, marker.label);
    kept.set(seriesIndex, forSeries);
  }
  return kept;
}

/** Every kept marker's label, in series then row order, for the summary. */
export function keptLabels(kept: MarkerLabels): string[] {
  return [...kept]
    .sort(([a], [b]) => a - b)
    .flatMap(([, byRow]) =>
      [...byRow].sort(([a], [b]) => a - b).map(([, label]) => label),
    );
}

/** The field carrying each row's own index on a bar chart with markers. */
export const ROW_KEY = "__row";

/**
 * The rows Recharts plots: `data` itself (same array) when nothing is
 * marked; on a bar chart, each row plus its index under `ROW_KEY`, which the
 * bar's marker label reads; on a line or area, `markerRows`.
 */
export function chartRows<Row extends ChartDatum>(
  data: readonly Row[],
  series: readonly ChartSeries<Row>[],
  kept: MarkerLabels,
  bars: boolean,
): readonly ChartDatum[] {
  if (kept.size === 0) {
    return data;
  }
  return bars
    ? data.map((row, rowIndex) => ({ ...row, [ROW_KEY]: rowIndex }))
    : markerRows(data, series, kept);
}

/**
 * For a line or area chart: `data` plus one `__marker_<i>` field per marked
 * series, holding the series value on marked rows and null elsewhere. The
 * rows are untouched (same array) when nothing is marked.
 */
export function markerRows<Row extends ChartDatum>(
  data: readonly Row[],
  series: readonly ChartSeries<Row>[],
  kept: MarkerLabels,
): readonly ChartDatum[] {
  if (kept.size === 0) {
    return data;
  }
  return data.map((row, rowIndex) => {
    const extra: Record<string, number | null> = {};
    for (const [seriesIndex, byRow] of kept) {
      extra[markerKey(seriesIndex)] = byRow.has(rowIndex)
        ? numberAt(row, series[seriesIndex].key)
        : null;
    }
    return { ...row, ...extra };
  });
}
