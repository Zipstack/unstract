import type { JSX } from "react";
import { CartesianChart } from "./CartesianChart";
import type { CartesianChartProps, ChartDatum } from "./types";

export type AreaChartProps<Row extends ChartDatum> = CartesianChartProps<Row>;

/** A line chart with a translucent fill under each series. Series overlap; they do not stack. */
export function AreaChart<Row extends ChartDatum>(
  props: AreaChartProps<Row>,
): JSX.Element {
  return <CartesianChart {...props} kind="area" slot="area-chart" />;
}
