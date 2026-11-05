import type { ReactElement } from "react";
import { usePlotArea } from "recharts";

/*
 * Renderers Recharts calls per point or per bar. Each decides only from what
 * Recharts hands it (the plotted `points`, the point's row as `payload`, the
 * label's `value`), never from the chart's props: Recharts updates its data
 * store after commit, so for one frame after a data change the points still
 * belong to the old rows, and anything taken from the new props would land
 * on the old geometry. Marker labels therefore travel in the rows
 * (`chartRows`).
 */

type Anchor = "start" | "middle" | "end";

/**
 * A marker: a dot ringed in the card colour, its label above; where the
 * label reads from is `labelAnchor`'s choice.
 */
function MarkerMark({
  x,
  y,
  color,
  label,
  anchor = "middle",
}: Readonly<{
  x: number;
  y: number;
  color: string;
  label: string;
  anchor?: Anchor;
}>) {
  return (
    <g data-slot="chart-marker">
      <circle
        cx={x}
        cy={y}
        r={4}
        fill={color}
        stroke="var(--card)"
        strokeWidth={2}
      />
      <text
        x={
          anchor === "start"
            ? x - LABEL_NUDGE
            : anchor === "end"
              ? x + LABEL_NUDGE
              : x
        }
        y={y - 10}
        textAnchor={anchor}
        className="ui:fill-foreground"
      >
        {label}
      </text>
    </g>
  );
}

type Point = Readonly<{ x?: number | null; y?: number | null }>;

type PointProps = Readonly<{
  cx?: number;
  cy?: number;
  index?: number;
  points?: readonly Point[];
  payload?: unknown;
}>;

// Caption type is 12px and averages about 0.6em a character. An estimate is
// enough to tell whether a centred label would cross the plot's edge.
const LABEL_CHAR_WIDTH = 7;

/** How far `MarkerMark` shifts a label read from one side of its dot. */
const LABEL_NUDGE = 4;

/**
 * Where a marker's label reads from, given the plot's left and right bounds:
 * whichever of `middle` (centred), `start` (rightward from the dot) or `end`
 * (leftward) leaves the least of the estimated label outside the bounds,
 * preferring `middle` on a tie, so a label that fits stays centred. Without
 * bounds it stays centred.
 */
function labelAnchor(
  cx: number,
  label: string,
  left: number | null | undefined,
  right: number | null | undefined,
): Anchor {
  if (typeof left !== "number" || typeof right !== "number") {
    return "middle";
  }
  const width = label.length * LABEL_CHAR_WIDTH;
  const overflow = (from: number) =>
    Math.max(0, left - from) + Math.max(0, from + width - right);
  const candidates: [Anchor, number][] = [
    ["middle", overflow(cx - width / 2)],
    ["start", overflow(cx - LABEL_NUDGE)],
    ["end", overflow(cx + LABEL_NUDGE - width)],
  ];
  let best = candidates[0];
  for (const candidate of candidates) {
    if (candidate[1] < best[1]) {
      best = candidate;
    }
  }
  return best[0];
}

/**
 * `dot` for a line or area's marker series: a marker on each marked row,
 * labelled from the row's `labelKey` field. Unmarked rows hold null for the
 * marker value, so they have no point.
 */
export function markerDot(color: string, labelKey: string) {
  return function MarkerDot({
    cx,
    cy,
    points,
    payload,
  }: PointProps): ReactElement {
    const label =
      typeof payload === "object" && payload !== null
        ? (payload as Record<string, unknown>)[labelKey]
        : undefined;
    if (cx === undefined || cy === undefined || typeof label !== "string") {
      return <g />;
    }
    // A category axis without bars puts the first and last row on the plot's
    // bounds. A single row sits mid-plot, with no bounds to read from.
    const anchor =
      points === undefined || points.length < 2
        ? "middle"
        : labelAnchor(cx, label, points[0]?.x, points[points.length - 1]?.x);
    return (
      <MarkerMark x={cx} y={cy} color={color} label={label} anchor={anchor} />
    );
  };
}

/**
 * `dot` for a line or area series: draws a point only where it has no
 * plotted neighbour (a single row, or a value between two gaps), which a
 * line cannot draw on its own: a one-point path paints nothing.
 */
export function isolatedDot(color: string) {
  return function IsolatedDot({
    cx,
    cy,
    index,
    points,
  }: PointProps): ReactElement {
    const plotted = (i: number) => points?.[i]?.y != null;
    if (
      cx === undefined ||
      cy === undefined ||
      index === undefined ||
      plotted(index - 1) ||
      plotted(index + 1)
    ) {
      return <g />;
    }
    return (
      <circle data-slot="chart-point" cx={cx} cy={cy} r={3} fill={color} />
    );
  };
}

type BarMarkerProps = Readonly<{
  color: string;
  // Set by Recharts, which clones this element per bar.
  x?: number | string;
  y?: number | string;
  width?: number | string;
  value?: unknown;
}>;

/**
 * `LabelList` content for a bar's markers, passed as an element so Recharts
 * clones it rather than mounting a new component type each render. Its
 * `dataKey` is the series' `markerLabelKey`, so `value` is the label carried
 * in that bar's own row (unmarked rows have none). Centred over the bar it
 * names, on top of its own segment in a stack, since Recharts gives the
 * bar's own geometry; near the plot's edges (Recharts' own plot area, so no
 * layout is restated here) the label reads inward as on a line.
 */
export function BarMarker({
  color,
  x,
  y,
  width,
  value,
}: BarMarkerProps): ReactElement {
  const plot = usePlotArea();
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof width !== "number" ||
    typeof value !== "string"
  ) {
    return <g />;
  }
  const cx = x + width / 2;
  const anchor = labelAnchor(
    cx,
    value,
    plot?.x,
    plot === undefined ? undefined : plot.x + plot.width,
  );
  return (
    <MarkerMark x={cx} y={y} color={color} label={value} anchor={anchor} />
  );
}
