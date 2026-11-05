import type { ReactElement } from "react";

/*
 * Renderers Recharts calls per point or per bar. Each decides from what
 * Recharts hands it (the plotted `points`, the label's `value`), never from
 * the chart's own `data`: Recharts updates its data store after commit, so
 * for one frame after a data change the points still belong to the old rows,
 * and a decision taken from the new rows would land on the old geometry.
 */

/** A marker: a dot ringed in the card colour, its label above. */
function MarkerMark({
  x,
  y,
  color,
  label,
}: Readonly<{ x: number; y: number; color: string; label: string }>) {
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
      <text x={x} y={y - 10} textAnchor="middle" className="ui:fill-foreground">
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
}>;

/**
 * `dot` for a line or area's marker series: a marker on each labelled row.
 * The marker values live in the rows themselves (`markerRows`), so a point
 * exists only where its row is marked.
 */
export function markerDot(color: string, labels: ReadonlyMap<number, string>) {
  return function MarkerDot({ cx, cy, index }: PointProps): ReactElement {
    const label = index === undefined ? undefined : labels.get(index);
    if (cx === undefined || cy === undefined || label === undefined) {
      return <g />;
    }
    return <MarkerMark x={cx} y={cy} color={color} label={label} />;
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
  labels: ReadonlyMap<number, string>;
  // Set by Recharts, which clones this element per bar.
  x?: number | string;
  y?: number | string;
  width?: number | string;
  value?: unknown;
}>;

/**
 * `LabelList` content for a bar's markers, passed as an element so Recharts
 * clones it rather than mounting a new component type each render. The
 * label's value is the row index (`dataKey={ROW_KEY}`, see `chartRows`), not LabelList's own
 * index: that counts drawn bars, and a gap draws none, so it drifts off the
 * row after the first gap. Centred over the bar it names, on top of its own
 * segment in a stack, since Recharts gives the bar's own geometry.
 */
export function BarMarker({
  color,
  labels,
  x,
  y,
  width,
  value,
}: BarMarkerProps): ReactElement {
  const label = typeof value === "number" ? labels.get(value) : undefined;
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof width !== "number" ||
    label === undefined
  ) {
    return <g />;
  }
  return <MarkerMark x={x + width / 2} y={y} color={color} label={label} />;
}
