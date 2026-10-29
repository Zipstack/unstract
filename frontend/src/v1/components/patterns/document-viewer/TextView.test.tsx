import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { expect, it, vi } from "vitest";
import type { PdfPageListHandle } from "./PdfPageList";
import { TextView } from "./TextView";

// Shaped like an LLMWhisperer layout result: columns kept with spaces.
const text = [
  "INVOICE                         No. 4471",
  "",
  "Bill to:   Acme Corp            Date: 2026-10-01",
  "Total due:                      $1,240.00",
].join("\n");

function line(container: HTMLElement, index: number): HTMLElement {
  const element = container.querySelector<HTMLElement>(
    `[data-line="${index}"]`,
  );
  if (!element) {
    throw new Error(`no line ${index}`);
  }
  return element;
}

it("shows every line, blank ones included, with its number", () => {
  const { container } = render(<TextView text={text} />);
  expect(container.querySelectorAll("[data-line]")).toHaveLength(4);
  expect(line(container, 3).textContent).toBe(
    "4Total due:                      $1,240.00",
  );
});

it("highlights whole lines in their tone, and the active one as active", () => {
  const { container } = render(
    <TextView
      text={text}
      highlights={[
        { id: "total", line: 3 },
        { id: "date", line: 2, tone: "low-confidence" },
      ]}
      activeHighlightId="total"
    />,
  );
  expect(line(container, 3).getAttribute("data-tone")).toBe("active");
  expect(line(container, 2).getAttribute("data-tone")).toBe("low-confidence");
  expect(line(container, 0).getAttribute("data-tone")).toBeNull();
});

it("reports clicks on highlighted lines only", async () => {
  const onHighlightClick = vi.fn();
  render(
    <TextView
      text={text}
      highlights={[{ id: "total", line: 3 }]}
      onHighlightClick={onHighlightClick}
    />,
  );
  const buttons = screen.getAllByRole("button");
  expect(buttons).toHaveLength(1);
  await userEvent.click(buttons[0] as HTMLElement);
  expect(onHighlightClick).toHaveBeenCalledWith({ id: "total", line: 3 });
});

it("centres a highlighted line on request", () => {
  const ref = createRef<PdfPageListHandle>();
  const { container } = render(
    <TextView ref={ref} text={text} highlights={[{ id: "total", line: 3 }]} />,
  );
  const root = screen.getByRole("region", { name: "Document text" });
  Object.defineProperty(root, "clientHeight", { value: 100 });
  Object.defineProperties(line(container, 3), {
    offsetTop: { value: 400 },
    offsetHeight: { value: 20 },
  });
  act(() => {
    expect(ref.current?.scrollToHighlight("total")).toBe(true);
  });
  expect(root.scrollTop).toBe(400 + 10 - 50);
  expect(ref.current?.scrollToHighlight("nope")).toBe(false);
});

it("shows the empty state for blank text", () => {
  render(<TextView text={"  \n "} />);
  expect(screen.getByText("No document")).toBeTruthy();
});
