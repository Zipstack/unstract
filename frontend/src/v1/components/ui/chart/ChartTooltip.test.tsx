import { render } from "@testing-library/react";
import { expect, it } from "vitest";
import { ChartTooltip } from "./ChartTooltip";

const series = [
  { key: "pages", label: "Pages", color: "var(--chart-1)", format: String },
];
const fmt = { value: String, x: String };

it("names the category from the hovered row when given a category key, not from the label", () => {
  // Recharts' label here is a row index (1); the row it hands over is the
  // one plotted, which is what the values belong to.
  const { container } = render(
    <ChartTooltip
      active
      label={1}
      payload={[
        {
          dataKey: "pages",
          value: 7,
          payload: { day: "plotted row", pages: 7 },
        },
      ]}
      series={series}
      fmt={fmt}
      categoryKey="day"
    />,
  );
  expect(container.querySelector("p")).toHaveTextContent("plotted row");
});

it("uses Recharts' label as the category without a category key", () => {
  const { container } = render(
    <ChartTooltip
      active
      label="10 Aug"
      payload={[{ dataKey: "pages", value: 7 }]}
      series={series}
      fmt={fmt}
    />,
  );
  expect(container.querySelector("p")).toHaveTextContent("10 Aug");
  expect(container).toHaveTextContent("Pages7");
});

it("renders nothing while inactive", () => {
  const { container } = render(
    <ChartTooltip active={false} series={series} fmt={fmt} />,
  );
  expect(container).toBeEmptyDOMElement();
});
