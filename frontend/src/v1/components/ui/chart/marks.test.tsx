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
 * comes from the plotted row (`payload`) or the label's `value`.
 */

function svg(element: ReactElement): SVGSVGElement {
  const { container } = render(<svg aria-hidden="true">{element}</svg>);
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

it("reads a line marker's label from wherever leaves least of it outside the plot", () => {
  const Dot = markerDot("var(--chart-1)", "l");
  // Plot edges at x 0 and 300; "peak" is about 28 wide.
  const points = [
    { x: 0, y: 1 },
    { x: 150, y: 2 },
    { x: 300, y: 3 },
  ];
  const text = (cx: number, label = "peak", of = points) =>
    svg(
      <Dot cx={cx} cy={20} points={of} payload={{ l: label }} />,
    ).querySelector("text");
  const anchor = (cx: number, label?: string, of?: typeof points) =>
    text(cx, label, of)?.getAttribute("text-anchor");
  expect(anchor(0)).toBe("start");
  expect(text(0)?.getAttribute("x")).toBe("-4");
  expect(anchor(150)).toBe("middle");
  expect(text(150)?.getAttribute("x")).toBe("150");
  expect(anchor(300)).toBe("end");
  expect(text(300)?.getAttribute("x")).toBe("304");
  // A long label, about 140 wide: centred it fits from 70 to 230.
  const long = "10 Aug · 2,981 pages";
  expect(anchor(40, long)).toBe("start");
  expect(anchor(69, long)).toBe("start");
  expect(anchor(70, long)).toBe("middle"); // fits exactly: centred wins the tie
  expect(anchor(100, long)).toBe("middle");
  expect(anchor(230, long)).toBe("middle");
  expect(anchor(231, long)).toBe("end");
  expect(anchor(260, long)).toBe("end");
  // On a narrow plot, reading inward would overflow the far edge more than
  // centring: centred spills 1 on the left, rightward would spill 55.
  const narrow = [
    { x: 0, y: 1 },
    { x: 150, y: 2 },
  ];
  expect(anchor(69, long, narrow)).toBe("middle");
  // ...but close to an edge, reading inward still spills less.
  expect(
    anchor(10, long, [
      { x: 0, y: 1 },
      { x: 100, y: 2 },
    ]),
  ).toBe("start");
  // Wider than the plot and dead centre: centring spills least.
  expect(
    anchor(50, long, [
      { x: 0, y: 1 },
      { x: 100, y: 2 },
    ]),
  ).toBe("middle");
  // The 4 nudge counts: on a 20-wide plot at x 3, "peak" read rightward
  // from x -1 spills 8, centred spills 11.
  expect(
    anchor(3, "peak", [
      { x: 0, y: 1 },
      { x: 20, y: 2 },
    ]),
  ).toBe("start");
  // ...and so does the mirror: at x 17, read leftward from x 21, it spills 8.
  expect(
    anchor(17, "peak", [
      { x: 0, y: 1 },
      { x: 20, y: 2 },
    ]),
  ).toBe("end");
  // A single row sits mid-plot.
  expect(anchor(150, "peak", [{ x: 150, y: 1 }])).toBe("middle");
});

it("centres a bar marker's label outside a chart, where there is no plot area", () => {
  // Inside a chart the bounds come from Recharts' plot area; see the bar
  // chart tests in charts.test.tsx.
  expect(
    svg(
      <BarMarker
        color="var(--chart-1)"
        x={0}
        y={5}
        width={10}
        value="10 Aug · 2,981 pages"
      />,
    )
      .querySelector("text")
      ?.getAttribute("text-anchor"),
  ).toBe("middle");
});
