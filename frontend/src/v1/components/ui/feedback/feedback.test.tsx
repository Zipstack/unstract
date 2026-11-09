import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { InlineAlert } from "./InlineAlert";
import { ProgressBar } from "./ProgressBar";
import {
  Skeleton,
  SkeletonAvatar,
  SkeletonTableRows,
  SkeletonText,
} from "./Skeleton";
import { Spinner } from "./Spinner";
import { StepProgress } from "./StepProgress";

it("announces an inline error at once and other kinds politely", () => {
  const { rerender } = render(<InlineAlert title="Could not load projects" />);
  expect(screen.getByRole("alert")?.textContent).toContain(
    "Could not load projects",
  );
  rerender(<InlineAlert kind="warning" title="Quota at 90%" />);
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("status")?.getAttribute("data-kind")).toBe("warning");
});

it("offers Retry only when given onRetry, and calls it", async () => {
  const user = userEvent.setup();
  const onRetry = vi.fn();
  const { rerender } = render(<InlineAlert title="Failed" />);
  expect(screen.queryByRole("button")).toBeNull();
  rerender(
    <InlineAlert title="Failed" onRetry={onRetry} retryLabel="Try again" />,
  );
  await user.click(screen.getByRole("button", { name: "Try again" }));
  expect(onRetry).toHaveBeenCalledOnce();
  // Not the click event: `onRetry={load}` must not receive it as an argument.
  expect(onRetry.mock.calls[0]).toEqual([]);
});

it("reports determinate progress, clamped to the range", () => {
  const { rerender } = render(<ProgressBar aria-label="Upload" value={40} />);
  const bar = screen.getByRole("progressbar", { name: "Upload" });
  expect(bar?.getAttribute("aria-valuenow")).toBe("40");
  expect(bar?.getAttribute("aria-valuemax")).toBe("100");
  rerender(<ProgressBar aria-label="Upload" value={140} />);
  expect(bar?.getAttribute("aria-valuenow")).toBe("100");
  rerender(<ProgressBar aria-label="Upload" value={-5} />);
  expect(bar?.getAttribute("aria-valuenow")).toBe("0");
  rerender(<ProgressBar aria-label="Upload" value={3} max={4} />);
  expect(bar?.getAttribute("aria-valuenow")).toBe("3");
  expect(bar?.getAttribute("aria-valuemax")).toBe("4");
});

it("fills the bar as a fraction of max", () => {
  const { container } = render(
    <ProgressBar aria-label="Upload" value={3} max={4} />,
  );
  const indicator = container.querySelector("[data-slot=progress-bar] > div");
  expect(indicator?.getAttribute("style")).toContain("--progress: 0.75");
});

it("shows an empty bar, not NaN, when the total is zero or invalid", () => {
  const { rerender, container } = render(
    <ProgressBar aria-label="Batch" value={0} max={0} />,
  );
  const bar = screen.getByRole("progressbar", { name: "Batch" });
  const indicator = container.querySelector("[data-slot=progress-bar] > div");
  expect(bar.getAttribute("aria-valuenow")).toBe("0");
  expect(indicator?.getAttribute("style")).toContain("--progress: 0");
  rerender(<ProgressBar aria-label="Batch" value={5} max={-3} />);
  expect(bar.getAttribute("aria-valuenow")).toBe("0");
  expect(bar.getAttribute("aria-valuemax")).toBe("100");
  // `done / total * 100` with total 0.
  rerender(<ProgressBar aria-label="Batch" value={Number.NaN} />);
  expect(bar.getAttribute("aria-valuenow")).toBe("0");
  expect(bar.getAttribute("data-state")).not.toBe("indeterminate");
  expect(indicator?.getAttribute("style")).toContain("--progress: 0");
  expect(indicator?.getAttribute("style")).not.toContain("NaN");
});

it("leaves aria-valuenow out while progress is indeterminate", () => {
  render(<ProgressBar aria-label="Extracting" />);
  const bar = screen.getByRole("progressbar", { name: "Extracting" });
  expect(bar?.hasAttribute("aria-valuenow")).toBe(false);
  expect(bar?.getAttribute("data-state")).toBe("indeterminate");
});

it("marks the current step and says each step's state", () => {
  render(
    <StepProgress
      aria-label="Setup"
      steps={["Source", "Prompt", "Destination"]}
      current={1}
    />,
  );
  const list = screen.getByRole("list", { name: "Setup" });
  const items = screen.getAllByRole("listitem");
  expect(list).not.toBeNull();
  expect(items.map((i) => i.dataset.state)).toEqual([
    "done",
    "current",
    "upcoming",
  ]);
  expect(items[1]?.getAttribute("aria-current")).toBe("step");
  expect(items[0]?.textContent).toContain("Source, completed");
  expect(items[2]?.textContent).toContain("Destination, not started");
});

it("marks every step done when current is past the end", () => {
  render(<StepProgress aria-label="Setup" steps={["A", "B"]} current={2} />);
  const states = screen.getAllByRole("listitem").map((i) => i.dataset.state);
  expect(states).toEqual(["done", "done"]);
});

it("exposes one status region with the label for a skeleton and hides the bars", () => {
  render(
    <Skeleton label="Loading projects">
      <SkeletonAvatar />
      <SkeletonText lines={4} />
      <SkeletonTableRows rows={2} columns={3} />
    </Skeleton>,
  );
  const region = screen.getByRole("status");
  // aria-busy would hold the announcement until the skeleton unmounts.
  expect(region.hasAttribute("aria-busy")).toBe(false);
  expect(region?.textContent).toContain("Loading projects");
  expect(
    region
      .querySelector("[aria-hidden=true]")
      ?.contains(
        region.querySelector("[data-slot=skeleton-text]") as HTMLElement,
      ),
  ).toBe(true);
});

it("draws text lines 12 then 10 tall, widths cycling 100%, 78%, 46%", () => {
  const { container } = render(<SkeletonText lines={4} />);
  const bars = [
    ...container.querySelectorAll("[data-slot=skeleton-text] > span"),
  ];
  expect(bars.map((b) => b.className.match(/ui:h-[\d.]+/)?.[0])).toEqual([
    "ui:h-3",
    "ui:h-2.5",
    "ui:h-2.5",
    "ui:h-2.5",
  ]);
  expect(bars.map((b) => b.className.match(/ui:w-\S+/)?.[0])).toEqual([
    "ui:w-full",
    "ui:w-[78%]",
    "ui:w-[46%]",
    "ui:w-full",
  ]);
});

it("names a spinner only when asked", () => {
  const { rerender } = render(<Spinner />);
  expect(screen.queryByRole("status")).toBeNull();
  rerender(<Spinner size="button" label="Saving" />);
  expect(screen.getByRole("status")?.textContent).toContain("Saving");
});
