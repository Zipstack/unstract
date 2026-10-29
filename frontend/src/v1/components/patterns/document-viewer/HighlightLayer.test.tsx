import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Highlight } from "@v1/lib/pdf/highlights";
import { expect, it, vi } from "vitest";
import { HighlightLayer } from "./HighlightLayer";

const line: Highlight = {
  id: "line-0",
  page: 0,
  x: 0,
  y: 0.25,
  w: 1,
  h: 0.02,
  variant: "line",
  tone: "default",
  confidence: 0.97,
};
const word: Highlight = {
  id: "word-0",
  page: 0,
  x: 0.5,
  y: 0.25,
  w: 0.1,
  h: 0.02,
  variant: "box",
  tone: "low-confidence",
  confidence: 0.62,
};

function box(container: HTMLElement, id: string): HTMLElement {
  const element = container.querySelector<HTMLElement>(
    `[data-highlight-id="${id}"]`,
  );
  if (!element) {
    throw new Error(`no highlight ${id}`);
  }
  return element;
}

it("places highlights as percentages of the page", () => {
  const { container } = render(<HighlightLayer highlights={[line, word]} />);
  const element = box(container, "word-0");
  expect(element.style.getPropertyValue("--hl-x")).toBe("50%");
  expect(element.style.getPropertyValue("--hl-y")).toBe("25%");
  expect(element.style.getPropertyValue("--hl-w")).toBe("10%");
  expect(element.style.getPropertyValue("--hl-h")).toBe("2%");
  expect(element.getAttribute("data-variant")).toBe("box");
  expect(box(container, "line-0").getAttribute("data-variant")).toBe("line");
});

it("shows each highlight's tone, and the active one as active", () => {
  const { container } = render(
    <HighlightLayer highlights={[line, word]} activeId="line-0" />,
  );
  expect(box(container, "line-0").getAttribute("data-tone")).toBe("active");
  expect(box(container, "word-0").getAttribute("data-tone")).toBe(
    "low-confidence",
  );
});

it("is not interactive without a click handler", () => {
  render(<HighlightLayer highlights={[line]} />);
  expect(screen.queryByRole("button")).toBeNull();
});

it("reports clicks with the highlight, and labels each button", async () => {
  const onHighlightClick = vi.fn();
  render(
    <HighlightLayer
      highlights={[line, word]}
      activeId="word-0"
      onHighlightClick={onHighlightClick}
    />,
  );
  const button = screen.getByRole("button", {
    name: "Highlight on page 1, 62% confidence",
  });
  expect(button.getAttribute("aria-current")).toBe("true");
  await userEvent.click(button);
  expect(onHighlightClick).toHaveBeenCalledWith(word);
});

it("renders nothing for a page without highlights", () => {
  const { container } = render(<HighlightLayer highlights={[]} />);
  expect(container.firstChild).toBeNull();
});
