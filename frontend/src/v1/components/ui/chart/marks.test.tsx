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
    <BarMarker
      color="var(--chart-2)"
      inset={{ left: 0, right: 0 }}
      x={10}
      y={5}
      width={20}
      value="spike"
    />,
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
      <BarMarker
        color="var(--chart-2)"
        inset={{ left: 0, right: 0 }}
        x={10}
        y={5}
        width={20}
      />,
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

it("reads a line marker's label inward only where, centred, it would cross one plot edge", () => {
  const Dot = markerDot("var(--chart-1)", "l");
  // Plot edges at x 0 and 300; "peak" is about 28 wide, so 14 either side.
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
  // A long label, about 140 wide: inward within 70 of an edge, centred past it.
  const long = "10 Aug · 2,981 pages";
  expect(anchor(40, long)).toBe("start");
  expect(anchor(69, long)).toBe("start");
  expect(anchor(70, long)).toBe("middle"); // exactly half: fits
  expect(anchor(100, long)).toBe("middle");
  expect(anchor(260, long)).toBe("end");
  // Wider than the room on both sides: centring overflows least.
  expect(
    anchor(50, long, [
      { x: 0, y: 1 },
      { x: 100, y: 2 },
    ]),
  ).toBe("middle");
  // A single row sits mid-plot.
  expect(anchor(150, "peak", [{ x: 150, y: 1 }])).toBe("middle");
});

it("reads a bar marker's label inward near the plot's edges, from the SVG box less the insets", () => {
  // SVG 0..400; plot 40..392.
  const label = (x: number, width = 10) =>
    svg(
      <BarMarker
        color="var(--chart-1)"
        inset={{ left: 40, right: 8 }}
        parentViewBox={{ x: 0, width: 400 }}
        x={x}
        y={5}
        width={width}
        value="10 Aug · 2,981 pages"
      />,
    )
      .querySelector("text")
      ?.getAttribute("text-anchor");
  expect(label(45)).toBe("start"); // centre 50, 10 from the plot's left
  expect(label(195)).toBe("middle");
  expect(label(375)).toBe("end"); // centre 380, 12 from the plot's right
  // Centre 325: 67 from the plot's right (inward) but 75 from the SVG's.
  expect(label(320)).toBe("end");
  // Without Recharts' box it stays centred.
  expect(
    svg(
      <BarMarker
        color="var(--chart-1)"
        inset={{ left: 40, right: 8 }}
        x={45}
        y={5}
        width={10}
        value="peak"
      />,
    )
      .querySelector("text")
      ?.getAttribute("text-anchor"),
  ).toBe("middle");
});
