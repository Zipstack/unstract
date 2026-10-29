import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ImageView } from "./ImageView";

function loadImage(width: number, height: number) {
  const image = screen.getByRole<HTMLImageElement>("img", { hidden: true });
  Object.defineProperties(image, {
    naturalWidth: { value: width },
    naturalHeight: { value: height },
  });
  fireEvent.load(image);
  return image;
}

it("shows loading until the image arrives, then sizes it by the zoom", () => {
  const onLoadSize = vi.fn();
  const { container, rerender } = render(
    <ImageView url="/scan.png" zoom={1} onLoadSize={onLoadSize} />,
  );
  expect(screen.getByRole("status")).toBeTruthy();
  loadImage(1200, 1600);
  expect(screen.queryByRole("status")).toBeNull();
  // Reported in points, so the viewer fits it like a page.
  expect(onLoadSize).toHaveBeenCalledWith({ width: 900, height: 1200 });

  const frame = container.querySelector<HTMLElement>("img")?.parentElement;
  expect(frame?.style.getPropertyValue("--page-width")).toBe("1200px");
  rerender(<ImageView url="/scan.png" zoom={0.5} onLoadSize={onLoadSize} />);
  expect(frame?.style.getPropertyValue("--page-width")).toBe("600px");
  expect(frame?.style.getPropertyValue("--page-height")).toBe("800px");
});

it("draws highlights over the image", () => {
  const { container } = render(
    <ImageView
      url="/scan.png"
      zoom={1}
      highlights={[
        {
          id: "h",
          page: 0,
          x: 0.1,
          y: 0.2,
          w: 0.3,
          h: 0.05,
          variant: "box",
          tone: "default",
        },
      ]}
    />,
  );
  loadImage(1200, 1600);
  expect(container.querySelector('[data-highlight-id="h"]')).not.toBeNull();
});

it("offers Retry when the image fails, and loads it again", async () => {
  render(<ImageView url="/missing.png" zoom={1} />);
  fireEvent.error(screen.getByRole("img", { hidden: true }));
  expect(screen.getByRole("alert").textContent).toContain("didn't load");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(screen.getByRole("status")).toBeTruthy();
  expect(screen.getByRole("img", { hidden: true })).toBeTruthy();
});
