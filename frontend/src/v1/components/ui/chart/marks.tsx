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
 * A marker: a dot ringed in the card colour and its label, above the dot
 * unless the caller places it (`labelX`, `labelY`); where the label reads
 * from is the `anchor`.
 */
function MarkerMark({
  x,
  y,
  color,
  label,
  anchor = "middle",
  labelX,
  labelY = y - 10,
}: Readonly<{
  x: number;
  y: number;
  color: string;
  label: string;
  anchor?: Anchor;
  /** The label's x; by default nudged from the dot by its anchor. */
  labelX?: number;
  /** The label's baseline; above the dot unless the caller moves it. */
  labelY?: number;
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
          labelX ??
          (anchor === "start"
            ? x - LABEL_NUDGE
            : anchor === "end"
              ? x + LABEL_NUDGE
              : x)
        }
        y={labelY}
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

/** From a negative bar's tip to its label's baseline: past the dot, one line down. */
const LABEL_BELOW = 16;

/** From the dot's centre to a label read beside it: past the dot and its ring. */
const LABEL_BESIDE = 8;

/** Lowers a label read beside the dot so the dot sits at its middle. */
const LABEL_MIDLINE = 4;

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
  /** Negative for a bar below zero, whose `y` is then its lower tip. */
  height?: number | string;
  value?: unknown;
}>;

/**
 * `LabelList` content for a bar's markers, passed as an element so Recharts
 * clones it rather than mounting a new component type each render. Its
 * `dataKey` is the series' `markerLabelKey`, so `value` is the label carried
 * in that bar's own row (unmarked rows have none). Centred on the bar it
 * names, at its tip (the top, or the bottom below zero; its own segment's
 * in a stack), since Recharts gives the bar's own geometry. Near the plot's
 * left and right edges (Recharts' own plot area, so no layout is restated
 * here) the label reads inward; at the bottom edge see the placement below.
 */
export function BarMarker({
  color,
  x,
  y,
  width,
  height,
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
  // A bar below zero has its tip at the bottom: read the label under the
  // tip, clear of the bar. Where the plot has no room under the tip (a tip
  // within LABEL_BELOW of the plot's bottom edge, as the lowest bar's often
  // is) the label reads beside the dot instead, on the side where less of it
  // leaves the plot, its baseline kept within the plot's bottom.
  const below = typeof height === "number" && height < 0;
  const bottom =
    plot === undefined ? Number.POSITIVE_INFINITY : plot.y + plot.height;
  let place: Readonly<{ anchor: Anchor; x?: number; y?: number }> = { anchor };
  if (below && y + LABEL_BELOW <= bottom) {
    place = { anchor, y: y + LABEL_BELOW };
  } else if (below) {
    const left = plot === undefined ? Number.NEGATIVE_INFINITY : plot.x;
    const right =
      plot === undefined ? Number.POSITIVE_INFINITY : plot.x + plot.width;
    const width = value.length * LABEL_CHAR_WIDTH;
    const overRight = Math.max(0, cx + LABEL_BESIDE + width - right);
    const overLeft = Math.max(0, left - (cx - LABEL_BESIDE - width));
    const labelY = Math.min(y + LABEL_MIDLINE, bottom);
    place =
      overRight <= overLeft
        ? { anchor: "start", x: cx + LABEL_BESIDE, y: labelY }
        : { anchor: "end", x: cx - LABEL_BESIDE, y: labelY };
  }
  return (
    <MarkerMark
      x={cx}
      y={y}
      color={color}
      label={value}
      anchor={place.anchor}
      labelX={place.x}
      labelY={place.y}
    />
  );
}
