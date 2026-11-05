import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { expect, it } from "vitest";
import { BarMarker, isolatedDot, markerDot } from "./marks";

/*
 * The renderers decide only from what Recharts hands them. That is what
 * keeps a marker paired with its point in the frame after a data change,
 * when Recharts still plots the previous rows (it updates its store after
 * commit). happy-dom flushes that update inside act(), so the frame itself
 * cannot be observed here; these tests pin the mechanism instead: the label
 * comes from the plotted row (`payload`) or the label's `value`, and a
 * renderer is given nothing else to take it from.
 */

function svg(element: ReactElement): SVGSVGElement {
  const { container } = render(<svg>{element}</svg>);
  return container.querySelector("svg") as SVGSVGElement;
}

it("draws a line marker from the label in the plotted row, nothing on rows without one", () => {
  const Dot = markerDot("var(--chart-1)", "__marker_label:pages");
  const marked = svg(
    <Dot cx={10} cy={20} payload={{ "__marker_label:pages": "peak" }} />,
  );
  expect(marked.querySelector("[data-slot=chart-marker]")).toHaveTextContent(
    "peak",
  );
  expect(marked.querySelector("circle")).toHaveAttribute("cx", "10");
  expect(
    svg(<Dot cx={10} cy={20} payload={{ pages: 3 }} />).querySelector(
      "[data-slot=chart-marker]",
    ),
  ).toBeNull();
  expect(
    svg(<Dot payload={{ "__marker_label:pages": "peak" }} />).querySelector(
      "[data-slot=chart-marker]",
    ),
  ).toBeNull();
});

it("draws a bar marker from the label value, centred over the bar", () => {
  const marked = svg(
    <BarMarker color="var(--chart-2)" x={10} y={5} width={20} value="spike" />,
  );
  expect(marked.querySelector("[data-slot=chart-marker]")).toHaveTextContent(
    "spike",
  );
  expect(marked.querySelector("circle")).toHaveAttribute("cx", "20");
  expect(marked.querySelector("circle")).toHaveAttribute(
    "fill",
    "var(--chart-2)",
  );
  expect(
    svg(
      <BarMarker color="var(--chart-2)" x={10} y={5} width={20} />,
    ).querySelector("[data-slot=chart-marker]"),
  ).toBeNull();
});

it("draws an isolated point only where neither plotted neighbour has a value", () => {
  const Dot = isolatedDot("var(--chart-1)");
  const at = (points: readonly { y: number | null }[], index: number) =>
    svg(<Dot cx={1} cy={1} index={index} points={points} />).querySelector(
      "[data-slot=chart-point]",
    );
  const gappy = [{ y: 1 }, { y: null }, { y: 3 }, { y: 4 }];
  expect(at(gappy, 0)).not.toBeNull(); // nothing left, a gap right
  expect(at(gappy, 2)).toBeNull(); // joined to row 3
  expect(at([{ y: 5 }], 0)).not.toBeNull(); // a single row
});
