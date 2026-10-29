import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ViewerToolbar, type ViewerToolbarProps } from "./ViewerToolbar";

function setup(overrides: Partial<ViewerToolbarProps> = {}) {
  const props: ViewerToolbarProps = {
    pageIndex: 0,
    pageCount: 12,
    zoom: 1.25,
    zoomMode: "custom",
    canZoomIn: true,
    canZoomOut: true,
    onPageChange: vi.fn(),
    onZoomIn: vi.fn(),
    onZoomOut: vi.fn(),
    onFitWidth: vi.fn(),
    onFitPage: vi.fn(),
    ...overrides,
  };
  render(<ViewerToolbar {...props} />);
  return props;
}

it("shows the page as n / N and the zoom as a percentage", () => {
  setup({ pageIndex: 2 });
  expect(screen.getByLabelText<HTMLInputElement>("Page").value).toBe("3");
  expect(screen.getByText("/ 12")).toBeTruthy();
  expect(screen.getByLabelText("Zoom level").textContent).toBe("125%");
});

it("pages back and forward, and stops at either end", async () => {
  const first = setup();
  expect(
    screen.getByRole<HTMLButtonElement>("button", { name: "Previous page" })
      .disabled,
  ).toBe(true);
  await userEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(first.onPageChange).toHaveBeenCalledWith(1);
});

it("disables Next on the last page", () => {
  setup({ pageIndex: 11 });
  expect(
    screen.getByRole<HTMLButtonElement>("button", { name: "Next page" })
      .disabled,
  ).toBe(true);
});

it("jumps to a typed page on Enter and restores a page out of range", async () => {
  const props = setup();
  const box = screen.getByLabelText<HTMLInputElement>("Page");
  await userEvent.clear(box);
  await userEvent.type(box, "5{Enter}");
  expect(props.onPageChange).toHaveBeenCalledWith(4);

  await userEvent.clear(box);
  await userEvent.type(box, "99{Enter}");
  expect(props.onPageChange).toHaveBeenCalledTimes(1);
  expect(box.value).toBe("1");
});

it("zooms, fits, and shows the active fit as pressed", async () => {
  const props = setup({ zoomMode: "fit-width", canZoomIn: false });
  expect(
    screen.getByRole<HTMLButtonElement>("button", { name: "Zoom in" }).disabled,
  ).toBe(true);
  await userEvent.click(screen.getByRole("button", { name: "Zoom out" }));
  await userEvent.click(screen.getByRole("button", { name: "Fit page" }));
  expect(props.onZoomOut).toHaveBeenCalled();
  expect(props.onFitPage).toHaveBeenCalled();
  expect(
    screen
      .getByRole("button", { name: "Fit width" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
});

it("is reachable with Tab, control by control", async () => {
  setup({ pageIndex: 3 });
  const order = [
    "Previous page",
    "Page",
    "Next page",
    "Zoom out",
    "Zoom in",
    "Fit width",
    "Fit page",
  ];
  for (const name of order) {
    await userEvent.tab();
    const focused = document.activeElement;
    const label =
      focused?.getAttribute("aria-label") ??
      (focused?.id
        ? document.querySelector(`label[for="${focused.id}"]`)?.textContent
        : null);
    expect(label).toBe(name);
  }
});
