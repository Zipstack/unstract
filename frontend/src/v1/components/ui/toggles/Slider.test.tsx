import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { Slider } from "./Slider";

const twoPlaces = (v: number) => v.toFixed(2);

it("names a single thumb from the label and speaks its value", () => {
  renderV1(
    <Slider
      label="Temperature"
      defaultValue={[0.7]}
      min={0}
      max={1}
      step={0.1}
      formatValue={twoPlaces}
    />,
  );
  const thumb = screen.getByRole("slider", { name: "Temperature" });
  expect(thumb).toHaveAttribute("aria-label", "Temperature");
  expect(thumb).toHaveAttribute("aria-valuenow", "0.7");
  expect(thumb).toHaveAttribute("aria-valuetext", "0.70");
});

it("arrows, Home and End move and clamp", async () => {
  const onValueChange = vi.fn();
  const { user } = renderV1(
    <Slider
      label="Top K"
      defaultValue={[5]}
      min={0}
      max={10}
      step={1}
      onValueChange={onValueChange}
    />,
  );
  const thumb = screen.getByRole("slider", { name: "Top K" });
  thumb.focus();
  await user.keyboard("{ArrowRight}");
  expect(thumb).toHaveAttribute("aria-valuenow", "6");
  expect(thumb).toHaveAttribute("aria-valuetext", "6");
  expect(onValueChange).toHaveBeenLastCalledWith([6]);
  await user.keyboard("{End}");
  expect(thumb).toHaveAttribute("aria-valuenow", "10");
  expect(onValueChange).toHaveBeenLastCalledWith([10]);
  await user.keyboard("{ArrowRight}");
  expect(thumb).toHaveAttribute("aria-valuenow", "10");
  await user.keyboard("{Home}");
  expect(thumb).toHaveAttribute("aria-valuenow", "0");
  expect(onValueChange).toHaveBeenLastCalledWith([0]);
});

it("names each thumb of a range", () => {
  renderV1(
    <Slider
      label="Pages"
      thumbLabels={["Minimum", "Maximum"]}
      defaultValue={[2, 8]}
      min={0}
      max={10}
    />,
  );
  expect(screen.getByRole("slider", { name: "Minimum" })).toHaveAttribute(
    "aria-valuenow",
    "2",
  );
  expect(screen.getByRole("slider", { name: "Maximum" })).toHaveAttribute(
    "aria-valuenow",
    "8",
  );
});

it("keeps Radix's range names when only the slider is labelled", () => {
  renderV1(<Slider label="Pages" defaultValue={[2, 8]} min={0} max={10} />);
  expect(screen.getByRole("slider", { name: "Minimum" })).toHaveAttribute(
    "aria-valuenow",
    "2",
  );
  expect(screen.getByRole("slider", { name: "Maximum" })).toHaveAttribute(
    "aria-valuenow",
    "8",
  );
});

it("names a single thumb from the caller's aria-labelledby", () => {
  renderV1(
    <>
      <span id="ext">Temperature</span>
      <Slider aria-labelledby="ext" defaultValue={[0.5]} max={1} step={0.1} />
    </>,
  );
  const thumb = screen.getByRole("slider", { name: "Temperature" });
  expect(thumb).toHaveAttribute("aria-labelledby", "ext");
});

it("keeps Radix's range names under a root aria-labelledby", () => {
  renderV1(
    <>
      <span id="ext">Pages</span>
      <Slider aria-labelledby="ext" defaultValue={[2, 8]} min={0} max={10} />
    </>,
  );
  expect(screen.getByRole("slider", { name: "Minimum" })).not.toHaveAttribute(
    "aria-labelledby",
  );
  expect(screen.getByRole("slider", { name: "Maximum" })).not.toHaveAttribute(
    "aria-labelledby",
  );
});

it("follows a controlled value", () => {
  const oneDecimal = (v: number) => v.toFixed(1);
  const { rerender } = renderV1(
    <Slider label="Top P" value={[30]} formatValue={oneDecimal} showValue />,
  );
  const thumb = screen.getByRole("slider", { name: "Top P" });
  expect(thumb).toHaveAttribute("aria-valuenow", "30");
  expect(thumb).toHaveAttribute("aria-valuetext", "30.0");
  expect(screen.getByText("30.0")).toBeVisible();
  rerender(
    <Slider label="Top P" value={[40]} formatValue={oneDecimal} showValue />,
  );
  expect(thumb).toHaveAttribute("aria-valuenow", "40");
  expect(thumb).toHaveAttribute("aria-valuetext", "40.0");
  expect(screen.getByText("40.0")).toBeVisible();
  expect(screen.queryByText("30.0")).toBeNull();
});

it("passes only the value to the formatter", () => {
  renderV1(
    <Slider
      label="Temperature"
      defaultValue={[0.5]}
      max={1}
      step={0.1}
      formatValue={(v: number, digits = 2) => v.toFixed(digits)}
      showValue
    />,
  );
  expect(screen.getByText("0.50")).toBeVisible();
});

it("names the thumb from a non-string label through aria-labelledby", () => {
  renderV1(<Slider label={<em>Temperature</em>} defaultValue={[50]} />);
  const thumb = screen.getByRole("slider", { name: "Temperature" });
  expect(thumb).not.toHaveAttribute("aria-label");
});

it("shows the formatted value when asked", () => {
  const { unmount } = renderV1(
    <Slider
      label="Temperature"
      defaultValue={[0.7]}
      min={0}
      max={1}
      step={0.1}
      formatValue={twoPlaces}
      showValue
    />,
  );
  expect(screen.getByText("0.70")).toBeVisible();
  unmount();
  renderV1(
    <Slider
      label="Temperature"
      defaultValue={[0.7]}
      min={0}
      max={1}
      step={0.1}
      formatValue={twoPlaces}
    />,
  );
  expect(screen.queryByText("0.70")).toBeNull();
});

it("shows a range joined by an en dash and follows uncontrolled changes", async () => {
  const { user } = renderV1(
    <Slider
      label="Pages"
      thumbLabels={["Minimum", "Maximum"]}
      defaultValue={[2, 8]}
      min={0}
      max={10}
      showValue
    />,
  );
  expect(screen.getByText("2 – 8")).toBeVisible();
  screen.getByRole("slider", { name: "Minimum" }).focus();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByText("3 – 8")).toBeVisible();
});

it("is described by its description on the thumb, keeping the caller's", () => {
  const { container } = renderV1(
    <>
      <span id="extra">Extra note</span>
      <Slider
        label="Temperature"
        description="Higher is more random"
        aria-describedby="extra"
        defaultValue={[50]}
      />
    </>,
  );
  const thumb = screen.getByRole("slider", { name: "Temperature" });
  expect(thumb).toHaveAccessibleDescription("Extra note Higher is more random");
  const group = screen.getByRole("group", { name: "Temperature" });
  expect(group).toBe(container.querySelector("[data-slot=slider]"));
  expect(group).toHaveAccessibleDescription("Extra note Higher is more random");
});

it("describes every thumb of a range", () => {
  renderV1(
    <Slider
      label="Pages"
      description="Inclusive"
      thumbLabels={["Minimum", "Maximum"]}
      defaultValue={[2, 8]}
    />,
  );
  for (const name of ["Minimum", "Maximum"]) {
    expect(screen.getByRole("slider", { name })).toHaveAccessibleDescription(
      "Inclusive",
    );
  }
});

it("renders only the slider when there is no label, description or value", () => {
  const { container } = renderV1(
    <Slider aria-label="Volume" defaultValue={[50]} />,
  );
  expect(screen.getByRole("slider", { name: "Volume" })).toBeInTheDocument();
  const field = container.querySelector("[data-slot=slider-field]");
  expect(field?.children).toHaveLength(1);
  expect(field?.firstElementChild).toHaveAttribute("data-slot", "slider");
});

it("is inert when disabled", async () => {
  const onValueChange = vi.fn();
  const { user, container } = renderV1(
    <Slider
      label="Temperature"
      disabled
      defaultValue={[50]}
      onValueChange={onValueChange}
    />,
  );
  const root = container.querySelector("[data-slot=slider]");
  expect(root).toHaveAttribute("data-disabled");
  expect(screen.getByText("Temperature")).toHaveAttribute("data-disabled");
  const thumb = screen.getByRole("slider", { name: "Temperature" });
  expect(thumb).toHaveAttribute("aria-disabled", "true");
  thumb.focus();
  await user.keyboard("{ArrowRight}");
  expect(thumb).toHaveAttribute("aria-valuenow", "50");
  expect(onValueChange).not.toHaveBeenCalled();
});

it("has the board's track and thumb sizes by class", () => {
  const { container } = renderV1(
    <Slider aria-label="Volume" defaultValue={[50]} />,
  );
  expect(screen.getByRole("slider", { name: "Volume" })).toBeInTheDocument();
  expect(container.querySelector("[data-slot=slider-track]")).toHaveClass(
    "ui:h-1.5",
    "ui:bg-muted",
  );
  expect(container.querySelector("[data-slot=slider-range]")).toHaveClass(
    "ui:bg-primary",
  );
  expect(container.querySelector("[data-slot=slider-thumb]")).toHaveClass(
    "ui:size-4",
    "ui:border-primary",
    "ui:focus-visible:focus-ring",
  );
});

it("leaves an enabled thumb without aria-disabled", () => {
  renderV1(<Slider aria-label="Volume" defaultValue={[50]} />);
  expect(screen.getByRole("slider", { name: "Volume" })).not.toHaveAttribute(
    "aria-disabled",
  );
});

it("treats a false label as absent", () => {
  const { container } = renderV1(
    <Slider label={false} aria-label="Volume" defaultValue={[50]} />,
  );
  const field = container.querySelector("[data-slot=slider-field]");
  expect(field?.children).toHaveLength(1);
  expect(screen.getByRole("slider", { name: "Volume" })).not.toHaveAttribute(
    "aria-labelledby",
  );
});

it("names the thumb from aria-label when the label is empty", () => {
  renderV1(<Slider label="" aria-label="Volume" defaultValue={[50]} />);
  expect(screen.getByRole("slider", { name: "Volume" })).toHaveAttribute(
    "aria-label",
    "Volume",
  );
});

it("puts className on the field, so the label line and track narrow together", () => {
  const { container } = renderV1(
    <Slider label="Volume" className="ui:max-w-xs" defaultValue={[50]} />,
  );
  expect(container.querySelector("[data-slot=slider-field]")).toHaveClass(
    "ui:max-w-xs",
  );
  expect(container.querySelector("[data-slot=slider]")).not.toHaveClass(
    "ui:max-w-xs",
  );
});

// Type-level guard, never rendered: the track is horizontal only.
export function _sliderHasNoOrientation() {
  // @ts-expect-error orientation is not supported
  return <Slider aria-label="Volume" orientation="vertical" />;
}
