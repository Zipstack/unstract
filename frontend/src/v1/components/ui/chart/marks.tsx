import type { ReactElement } from "react";

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
 * A marker: a dot ringed in the card colour, its label above. The label is
 * centred on the dot, except at the first and last point of a line or area,
 * which sit on the plot's edges: there it reads inward from the dot, so it
 * stays inside the chart instead of being cut off or covering the axis.
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
        x={anchor === "start" ? x - 4 : anchor === "end" ? x + 4 : x}
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

/**
 * `dot` for a line or area's marker series: a marker on each marked row,
 * labelled from the row's `labelKey` field. Unmarked rows hold null for the
 * marker value, so they have no point.
 */
export function markerDot(color: string, labelKey: string) {
  return function MarkerDot({
    cx,
    cy,
    index,
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
    const count = points?.length ?? 0;
    const anchor: Anchor =
      count < 2 || index === undefined
        ? "middle"
        : index === 0
          ? "start"
          : index === count - 1
            ? "end"
            : "middle";
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
 * bar's own geometry.
 */
export function BarMarker({
  color,
  x,
  y,
  width,
  value,
}: BarMarkerProps): ReactElement {
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof width !== "number" ||
    typeof value !== "string"
  ) {
    return <g />;
  }
  return <MarkerMark x={x + width / 2} y={y} color={color} label={value} />;
}
