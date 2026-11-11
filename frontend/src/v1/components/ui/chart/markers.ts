import { numberAt } from "./describe";
import type { ChartDatum, ChartMarker, ChartSeries } from "./types";

/*
 * Markers are drawn from the data, never with Recharts' ReferenceLine or
 * ReferenceDot. Those address a point by its category value, and on a
 * categorical axis that is the known defect: when a category label repeats
 * (the default `allowDuplicatedCategory`, e.g. "Mon" across two weeks or
 * "10 Aug" across two years) recharts 3.7.0 silently draws nothing, and even
 * when it draws, the marker cannot say which of two equal labels it means. A
 * marker here is indexed by row, and its value and label travel in the row
 * itself, so it always lands on the point it names: on a line or area as a
 * dot-only series aligned to the row, on a bar from the bar itself (so it
 * sits on its own bar's tip in a group, and on its own segment's tip in a
 * stack). `charts.test.tsx` asserts no reference element is ever rendered.
 */

/** Fields the chart adds to marked rows start with this; series keys may not. */
export const RESERVED_PREFIX = "__marker";

/*
 * The marker fields are named by series key, not position, so a chart that
 * keeps a series across a change (another series removed or reordered)
 * reads its own fields, in the previous rows as in the new ones.
 */

/** The field holding a series' marker value on a marked row (line and area). */
export function markerKey(seriesKey: string): string {
  return `${RESERVED_PREFIX}:${seriesKey}`;
}

/** The field holding a series' marker label on a marked row. */
export function markerLabelKey(seriesKey: string): string {
  return `${RESERVED_PREFIX}_label:${seriesKey}`;
}

/** True when a series key could collide with the marker fields. */
export function isReservedKey(seriesKey: string): boolean {
  return seriesKey.startsWith(RESERVED_PREFIX);
}

/** Marker labels by row index, for each series that has at least one. */
export type MarkerLabels = ReadonlyMap<number, ReadonlyMap<number, string>>;

/** A marker that will not be drawn, and why; the chart warns about these. */
export type DroppedMarker = Readonly<{ label: string; reason: string }>;

/**
 * The markers that will be drawn, by series index then row index, and the
 * ones that will not. The one rule for which markers count, used by the plot
 * and the summary alike: no series key is reserved (`isReservedKey`), the
 * series is charted, the index is an integer row of `data`, the series has a
 * value on that row, and no earlier marker already labels that point.
 * Anything else is dropped, never drawn and never read out; the chart warns
 * about each drop when it is showing data.
 */
export function keptMarkers<Row extends ChartDatum>(
  data: readonly Row[],
  series: readonly ChartSeries<Row>[],
  markers: readonly ChartMarker<Row>[],
): Readonly<{ kept: MarkerLabels; dropped: readonly DroppedMarker[] }> {
  const kept = new Map<number, Map<number, string>>();
  const dropped: DroppedMarker[] = [];
  // A reserved series key could be overwritten by the marker fields, so a
  // chart with one draws no markers at all (and warns about the key).
  const reserved = series.some((s) => isReservedKey(s.key));
  for (const marker of markers) {
    const seriesIndex = series.findIndex((s) => s.key === marker.series);
    const reason = reserved
      ? `a series key starts with "${RESERVED_PREFIX}", which markers reserve`
      : seriesIndex === -1
        ? "its series is not charted"
        : !Number.isInteger(marker.index) ||
            marker.index < 0 ||
            marker.index >= data.length
          ? `row ${marker.index} is not a row of data (${data.length} rows)`
          : numberAt(data[marker.index], marker.series) === null
            ? "the series has no value on that row"
            : kept.get(seriesIndex)?.has(marker.index)
              ? "an earlier marker already labels that point"
              : null;
    if (reason !== null) {
      dropped.push({ label: marker.label, reason });
      continue;
    }
    const forSeries = kept.get(seriesIndex) ?? new Map<number, string>();
    forSeries.set(marker.index, marker.label);
    kept.set(seriesIndex, forSeries);
  }
  return { kept, dropped };
}

/** Every kept marker's label, in series then row order, for the summary. */
export function keptLabels(kept: MarkerLabels): string[] {
  return [...kept]
    .sort(([a], [b]) => a - b)
    .flatMap(([, byRow]) =>
      [...byRow].sort(([a], [b]) => a - b).map(([, label]) => label),
    );
}

/** The console warning for each series key the chart reserves for markers. */
export function reservedKeyWarnings<Row extends ChartDatum>(
  series: readonly ChartSeries<Row>[],
): string[] {
  return series
    .filter((s) => isReservedKey(s.key))
    .map(
      (s) =>
        `Chart series key "${s.key}" starts with "${RESERVED_PREFIX}", which the chart uses for markers; rename the field.`,
    );
}

/** The console warning for each dropped marker. */
export function droppedWarnings(dropped: readonly DroppedMarker[]): string[] {
  return dropped.map(
    (d) => `Chart marker "${d.label}" not drawn: ${d.reason}.`,
  );
}

/**
 * The rows Recharts plots: `data` itself (same array) when nothing is
 * marked; otherwise each row plus, for each marked series, on a line or area
 * its value field (`markerKey`: the series value on rows it marks, null on
 * the rest, so the marker series draws nothing there) and, on rows it marks,
 * its label (`markerLabelKey`). Carrying both in the row keeps a marker paired with its point in
 * every frame: Recharts updates its data store after commit, so anything
 * the renderers took from props instead could meet the previous rows.
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
  return data.map((row, rowIndex) => {
    const extra: Record<string, number | string | null> = {};
    for (const [seriesIndex, byRow] of kept) {
      const key = series[seriesIndex].key;
      const label = byRow.get(rowIndex);
      if (!bars) {
        extra[markerKey(key)] = label === undefined ? null : numberAt(row, key);
      }
      if (label !== undefined) {
        extra[markerLabelKey(key)] = label;
      }
    }
    return { ...row, ...extra };
  });
}
