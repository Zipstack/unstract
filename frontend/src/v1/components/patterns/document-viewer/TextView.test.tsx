import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, type RefObject } from "react";
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

/**
 * Renders a highlight on a line that is one row high until the browser draws
 * it, then three; `draw()` draws it and runs the next animation frame.
 */
function withWrappedHighlight(
  check: (view: {
    ref: RefObject<PdfPageListHandle | null>;
    root: HTMLElement;
    draw: () => void;
  }) => void,
) {
  vi.useFakeTimers({
    toFake: ["requestAnimationFrame", "cancelAnimationFrame"],
  });
  try {
    const ref = createRef<PdfPageListHandle>();
    const { container } = render(
      <TextView
        ref={ref}
        text={text}
        highlights={[{ id: "total", line: 3 }]}
      />,
    );
    const root = screen.getByRole("region", { name: "Document text" });
    Object.defineProperty(root, "clientHeight", { value: 100 });
    let height = 20;
    Object.defineProperties(line(container, 3), {
      offsetTop: { value: 400 },
      offsetHeight: { get: () => height },
    });
    check({
      ref,
      root,
      draw: () => {
        height = 60;
        act(() => {
          vi.advanceTimersToNextFrame();
        });
      },
    });
  } finally {
    vi.useRealTimers();
  }
}

it("centres a wrapped line again once the browser has drawn it", () => {
  withWrappedHighlight(({ ref, root, draw }) => {
    act(() => {
      ref.current?.scrollToHighlight("total");
    });
    expect(root.scrollTop).toBe(400 + 10 - 50);
    draw();
    expect(root.scrollTop).toBe(400 + 30 - 50);
  });
});

it("lets a later jump to the top win over a highlight still being centred", () => {
  withWrappedHighlight(({ ref, root, draw }) => {
    act(() => {
      ref.current?.scrollToHighlight("total");
      ref.current?.scrollToPage(0);
    });
    draw();
    expect(root.scrollTop).toBe(0);
  });
});

it("says no text was found for blank text, not that there is no document", () => {
  render(<TextView text={"  \n "} />);
  expect(screen.getByText("No text found")).toBeTruthy();
  expect(screen.queryByText("No document")).toBeNull();
});

it("gives every row one gutter, as wide as the longest line number", () => {
  const text = Array.from({ length: 120 }, (_, n) => `line ${n}`).join("\n");
  const { container } = render(<TextView text={text} />);
  const list = container.querySelector<HTMLElement>("ol");
  expect(list?.style.getPropertyValue("--gutter")).toBe("3ch");
  const rows = container.querySelectorAll("li");
  expect(rows[8]?.className).toBe(rows[119]?.className);
  expect(rows[8]?.className).toContain("grid-cols-[var(--gutter)_1fr]");
});

it("lets the browser skip lines that are off screen, keeping them in the DOM", () => {
  const text = Array.from({ length: 50 }, (_, n) => `line ${n}`).join("\n");
  const { container } = render(<TextView text={text} />);
  const lines = container.querySelectorAll("li");
  expect(lines).toHaveLength(50);
  expect(lines[49]?.className).toContain("[content-visibility:auto]");
});
