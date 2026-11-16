import type { JSX } from "react";
import { CartesianChart } from "./CartesianChart";
import type { CartesianChartProps, ChartDatum } from "./types";

export type LineChartProps<Row extends ChartDatum> = CartesianChartProps<Row>;

/** Trends over a category axis, one line per series (frames D01, D14). */
export function LineChart<Row extends ChartDatum>(
  props: LineChartProps<Row>,
): JSX.Element {
  return <CartesianChart {...props} kind="line" slot="line-chart" />;
}
