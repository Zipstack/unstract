import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ChartTooltip } from "./ChartTooltip";

const series = [
  { key: "pages", label: "Pages", color: "var(--chart-1)", format: String },
];
const fmt = { value: String, x: String };

/*
 * The sparkline's heading used to be looked up in its `data` prop by row
 * index; it now comes from the row Recharts hands over with the values. The
 * two only differ for the frame before Recharts' store takes new data, which
 * happy-dom flushes inside act(), so no chart-level test can see it. The
 * category-key tests below pin the mechanism instead: the heading is read
 * from that row and never from the label.
 */
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

it("names no category, and does not throw, when the hovered row is missing", () => {
  const { container } = render(
    <ChartTooltip
      active
      label={1}
      payload={[]}
      series={series}
      fmt={fmt}
      categoryKey="day"
    />,
  );
  expect(container.querySelector("p")).toBeNull();
  expect(container).toHaveTextContent("Pages–");
});

it("speaks a gap as no data, with no category and no stray separator", () => {
  const onAnnounce = vi.fn();
  render(
    <ChartTooltip
      active
      label={1}
      payload={[]}
      series={series}
      fmt={fmt}
      categoryKey="day"
      onAnnounce={onAnnounce}
    />,
  );
  expect(onAnnounce).toHaveBeenLastCalledWith("Pages no data");
});

it("clears the sentence when it unmounts while open", () => {
  const onAnnounce = vi.fn();
  const { unmount } = render(
    <ChartTooltip
      active
      label="10 Aug"
      payload={[{ dataKey: "pages", value: 7 }]}
      series={series}
      fmt={fmt}
      onAnnounce={onAnnounce}
    />,
  );
  expect(onAnnounce).toHaveBeenLastCalledWith("10 Aug: Pages 7");
  unmount();
  expect(onAnnounce).toHaveBeenLastCalledWith("");
});

it("names no category when the hovered row lacks the category key, rather than the label", () => {
  const { container } = render(
    <ChartTooltip
      active
      label={1}
      payload={[{ dataKey: "pages", value: 7, payload: { pages: 7 } }]}
      series={series}
      fmt={fmt}
      categoryKey="day"
    />,
  );
  expect(container.querySelector("p")).toBeNull();
  expect(container).toHaveTextContent("Pages7");
});

it("names no category, and does not throw, when the hovered row is null", () => {
  const { container } = render(
    <ChartTooltip
      active
      label={1}
      payload={[{ dataKey: "pages", value: 7, payload: null }]}
      series={series}
      fmt={fmt}
      categoryKey="day"
    />,
  );
  expect(container.querySelector("p")).toBeNull();
  expect(container).toHaveTextContent("Pages7");
});

it("reports the active point's sentence while open and an empty one when closed", () => {
  const onAnnounce = vi.fn();
  const view = (active: boolean, value = 7) => (
    <ChartTooltip
      active={active}
      label="10 Aug"
      payload={[{ dataKey: "pages", value }]}
      series={series}
      fmt={fmt}
      onAnnounce={onAnnounce}
    />
  );
  const { rerender } = render(view(false));
  expect(onAnnounce).toHaveBeenLastCalledWith("");
  rerender(view(true));
  expect(onAnnounce).toHaveBeenLastCalledWith("10 Aug: Pages 7");
  rerender(view(true, 8));
  expect(onAnnounce).toHaveBeenLastCalledWith("10 Aug: Pages 8");
  rerender(view(false));
  expect(onAnnounce).toHaveBeenLastCalledWith("");
});
