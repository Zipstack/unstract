import type { JSX } from "react";
import { CartesianChart } from "./CartesianChart";
import type { CartesianChartProps, ChartDatum } from "./types";

export type StackedBarChartProps<Row extends ChartDatum> =
  CartesianChartProps<Row>;

/**
 * Series stacked into one bar per category, first series at the bottom
 * (LLMWhisperer frame D01, pages by mode). Order series as the ramp reads,
 * lightest first. Series on the right axis form their own stack.
 */
export function StackedBarChart<Row extends ChartDatum>(
  props: StackedBarChartProps<Row>,
): JSX.Element {
  return (
    <CartesianChart {...props} kind="stacked-bar" slot="stacked-bar-chart" />
  );
}
