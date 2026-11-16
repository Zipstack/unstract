import type { JSX } from "react";
import { CartesianChart } from "./CartesianChart";
import type { CartesianChartProps, ChartDatum } from "./types";

export type BarChartProps<Row extends ChartDatum> = CartesianChartProps<Row>;

/** One bar per series per category, side by side. */
export function BarChart<Row extends ChartDatum>(
  props: BarChartProps<Row>,
): JSX.Element {
  return <CartesianChart {...props} kind="bar" slot="bar-chart" />;
}
