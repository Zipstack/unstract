import type { ReactElement } from "react";
import { numberAt } from "./describe";
import type { ChartDatum } from "./types";

type PointProps = Readonly<{
  cx?: number;
  cy?: number;
  index?: number;
}>;

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

/** `dot` for a line or area's marker series: a marker on each labelled row. */
export function markerDot(color: string, labels: ReadonlyMap<number, string>) {
  return function MarkerDot({ cx, cy, index }: PointProps): ReactElement {
    const label = index === undefined ? undefined : labels.get(index);
    if (cx === undefined || cy === undefined || label === undefined) {
      return <g key={`none-${index}`} />;
    }
    return (
      <MarkerMark
        key={`marker-${index}`}
        x={cx}
        y={cy}
        color={color}
        label={label}
      />
    );
  };
}

type BarLabelProps = Readonly<{
  x?: number | string;
  y?: number | string;
  width?: number | string;
  index?: number;
}>;

/**
 * `LabelList` content for a bar's markers: centred over the bar it names, on
 * top of its own segment in a stack. Recharts gives the bar's own geometry,
 * so a grouped bar's offset within its category is already applied.
 */
export function barMarker(color: string, labels: ReadonlyMap<number, string>) {
  return function BarMarker({
    x,
    y,
    width,
    index,
  }: BarLabelProps): ReactElement {
    const label = index === undefined ? undefined : labels.get(index);
    if (
      typeof x !== "number" ||
      typeof y !== "number" ||
      typeof width !== "number" ||
      label === undefined
    ) {
      return <g key={`none-${index}`} />;
    }
    return (
      <MarkerMark
        key={`marker-${index}`}
        x={x + width / 2}
        y={y}
        color={color}
        label={label}
      />
    );
  };
}

/**
 * `dot` for a line or area series: draws a point only where it has no
 * defined neighbour (a single row, or a value between two gaps), which a
 * line cannot draw on its own: a one-point path paints nothing.
 */
export function isolatedDot(
  color: string,
  rows: readonly ChartDatum[],
  key: string,
) {
  return function IsolatedDot({ cx, cy, index }: PointProps): ReactElement {
    const defined = (i: number) =>
      i >= 0 && i < rows.length && numberAt(rows[i], key) !== null;
    if (
      cx === undefined ||
      cy === undefined ||
      index === undefined ||
      !defined(index) ||
      defined(index - 1) ||
      defined(index + 1)
    ) {
      return <g key={`none-${index}`} />;
    }
    return (
      <circle
        key={`point-${index}`}
        data-slot="chart-point"
        cx={cx}
        cy={cy}
        r={3}
        fill={color}
      />
    );
  };
}
