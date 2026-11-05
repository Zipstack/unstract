import { numberAt } from "./describe";
import type { ChartDatum, ChartMarker, ChartSeries } from "./types";

/*
 * Markers are drawn from the data, as a dot-only series, never with Recharts'
 * ReferenceLine or ReferenceDot. Those address a point by its category value,
 * and on a categorical axis that is the known defect: when a category label
 * repeats (the default `allowDuplicatedCategory`, e.g. "Mon" across two weeks
 * or "10 Aug" across two years) recharts 3.7.0 silently draws nothing, and
 * even when it draws, the marker cannot say which of two equal labels it
 * means. A marker series is indexed by row, so it always lands on the point
 * it names. `charts.test.tsx` asserts no reference element is ever rendered.
 */

/** The dataKey of series `seriesIndex`'s marker values in the augmented rows. */
export function markerKey(seriesIndex: number): string {
  return `__marker_${seriesIndex}`;
}

export type MarkerPlan = Readonly<{
  /** `data` plus one `__marker_<i>` field per marked series, null on unmarked rows. */
  rows: readonly ChartDatum[];
  /** For each marked series: its index, and the label at each marked row. */
  series: readonly Readonly<{
    seriesIndex: number;
    labels: ReadonlyMap<number, string>;
  }>[];
}>;

/**
 * Places each marker on its series. In a stacked chart the dot sits on top of
 * the series' segment, so its value is the running total up to that series.
 * A marker naming an unknown series or a row outside `data` is ignored.
 */
export function planMarkers<Row extends ChartDatum>(
  data: readonly Row[],
  series: readonly ChartSeries<Row>[],
  markers: readonly ChartMarker<Row>[],
  stacked: boolean,
): MarkerPlan {
  const labels = new Map<number, Map<number, string>>();
  for (const marker of markers) {
    const seriesIndex = series.findIndex((s) => s.key === marker.series);
    if (
      seriesIndex === -1 ||
      !Number.isInteger(marker.index) ||
      marker.index < 0 ||
      marker.index >= data.length
    ) {
      continue;
    }
    const forSeries = labels.get(seriesIndex) ?? new Map<number, string>();
    forSeries.set(marker.index, marker.label);
    labels.set(seriesIndex, forSeries);
  }
  if (labels.size === 0) {
    return { rows: data, series: [] };
  }
  const rows = data.map((row, rowIndex) => {
    const extra: Record<string, number | null> = {};
    for (const [seriesIndex, byRow] of labels) {
      const value = numberAt(row, series[seriesIndex].key);
      if (!byRow.has(rowIndex) || value === null) {
        extra[markerKey(seriesIndex)] = null;
        continue;
      }
      extra[markerKey(seriesIndex)] = stacked
        ? series
            .slice(0, seriesIndex + 1)
            .filter(
              (s) =>
                (s.axis ?? "left") === (series[seriesIndex].axis ?? "left"),
            )
            .reduce((sum, s) => sum + (numberAt(row, s.key) ?? 0), 0)
        : value;
    }
    return { ...row, ...extra };
  });
  return {
    rows,
    series: [...labels].map(([seriesIndex, byRow]) => ({
      seriesIndex,
      labels: byRow,
    })),
  };
}
