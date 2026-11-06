import { screen } from "@testing-library/react";
import { formatJson } from "@v1/lib/code/json-lines";
import { renderV1 } from "@v1/test";
import { expect, it } from "vitest";
import { DiffSummary, DiffView } from "./DiffView";

const OLD = "# Task\n\nreturning null.\n## Schema";
const NEW =
  "# Task\n\nreturning null. Dates as printed\n(MM/DD/YY).\n## Schema";

const cells = (container: HTMLElement, kind: string) =>
  [
    ...container.querySelectorAll(`[data-slot=diff-cell][data-kind=${kind}]`),
  ].map((c) => c.textContent);

it("summarises the change as in frame V12", () => {
  renderV1(<DiffView oldText={OLD} newText={NEW} />);
  const summary = screen.getByText("1 change").parentElement as HTMLElement;
  expect(summary.textContent).toBe("1 change+22 lines added−11 line removed");
});

it("pairs the changed lines side by side, marked for colour-blind and screen-reader users", () => {
  const { container } = renderV1(
    <DiffView
      oldText={OLD}
      newText={NEW}
      language="markdown"
      oldLabel="v1 - Auto-generated prompt"
      newLabel="v2 - Tightened date handling"
    />,
  );
  expect(screen.getByText("v1 - Auto-generated prompt")).toBeTruthy();
  expect(cells(container, "removed")).toEqual(["3−Removed: returning null."]);
  expect(cells(container, "added")).toEqual([
    "3+Added: returning null. Dates as printed",
    "4+Added: (MM/DD/YY).",
  ]);
  // The second added line has nothing opposite it.
  expect(cells(container, "empty")).toEqual([""]);
  expect(container.querySelectorAll("[data-slot=diff-row]")).toHaveLength(5);
  expect(container.querySelector(".ui\\:text-code-keyword")?.textContent).toBe(
    "# Task",
  );
});

it("lists removals before additions in one column when unified", () => {
  const { container } = renderV1(
    <DiffView
      oldText={OLD}
      newText={NEW}
      layout="unified"
      oldLabel="ignored"
    />,
  );
  expect(screen.queryByText("ignored")).toBeNull();
  const rows = [...container.querySelectorAll("[data-slot=diff-row]")].map(
    (r) => [r.getAttribute("data-kind"), r.textContent],
  );
  expect(rows).toEqual([
    ["context", "11 # Task"],
    ["context", "22 "],
    ["removed", "3−Removed: returning null."],
    ["added", "3+Added: returning null. Dates as printed"],
    ["added", "4+Added: (MM/DD/YY)."],
    ["context", "45 ## Schema"],
  ]);
});

it("says so when nothing changed, and can drop the summary and numbers", () => {
  const { container, rerender } = renderV1(
    <DiffView oldText="same" newText="same" />,
  );
  expect(screen.getByText("No changes")).toBeTruthy();
  rerender(<DiffView oldText="same" newText={"same\r\n"} />);
  expect(screen.getByText("Only line endings differ")).toBeTruthy();
  expect(container.querySelector("[data-kind=added]")).toBeNull();
  rerender(
    <DiffView
      oldText="a"
      newText="b"
      showSummary={false}
      showLineNumbers={false}
      wrap={false}
    />,
  );
  expect(container.querySelector("[data-slot=diff-summary]")).toBeNull();
  expect(cells(container, "removed")).toEqual(["−Removed: a"]);
  expect(
    container.querySelector("[data-slot=diff-cell] > span:last-child")
      ?.className,
  ).toMatch(/ui:whitespace-pre(\s|$)/);
});

it("diffs JSON through formatJson, as frame H20 does", () => {
  const { container } = renderV1(
    <DiffView
      oldText={formatJson({ shipper_city: "Newark", shipper_state: "NJ" })}
      newText={formatJson({ shipper_city: "Florence", shipper_state: "NJ" })}
      language="json"
      oldLabel="BEFORE"
      newLabel="AFTER"
    />,
  );
  expect(cells(container, "removed")).toEqual([
    '2−Removed:   "shipper_city": "Newark",',
  ]);
  expect(container.querySelector(".ui\\:text-code-key")?.textContent).toBe(
    '"shipper_city"',
  );
});

it("is a named, focusable region that passes axe in every mode", async () => {
  for (const theme of ["light", "dark", "unstract"] as const) {
    for (const layout of ["split", "unified"] as const) {
      const { container, unmount } = renderV1(
        <DiffView
          oldText={OLD}
          newText={NEW}
          layout={layout}
          oldLabel="A"
          newLabel="B"
        />,
        { theme },
      );
      expect(screen.getByRole("region", { name: "Changes" }).tabIndex).toBe(0);
      await expect(container).toHaveNoA11yViolations();
      unmount();
    }
  }
});

it("DiffSummary stands alone", () => {
  renderV1(
    <DiffSummary
      stats={{ changes: 3, added: 1, removed: 0, endingsOnly: false }}
    />,
  );
  expect(screen.getByText("3 changes")).toBeTruthy();
  expect(screen.getByText("1 line added")).toBeTruthy();
  expect(screen.getByText("0 lines removed")).toBeTruthy();
});
