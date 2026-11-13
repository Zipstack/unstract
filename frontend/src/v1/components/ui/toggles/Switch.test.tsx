import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { Switch } from "./Switch";

it("exposes its on and off state as a switch", async () => {
  const onCheckedChange = vi.fn();
  const { user } = renderV1(
    <Switch label="Dark mode" onCheckedChange={onCheckedChange} />,
  );
  const control = screen.getByRole("switch", { name: "Dark mode" });
  expect(control).toHaveAttribute("aria-checked", "false");

  await user.click(control);
  expect(control).toHaveAttribute("aria-checked", "true");
  expect(onCheckedChange).toHaveBeenLastCalledWith(true);

  control.focus();
  await user.keyboard(" ");
  expect(control).toHaveAttribute("aria-checked", "false");
  expect(onCheckedChange).toHaveBeenLastCalledWith(false);
  expect(onCheckedChange.mock.calls).toEqual([[true], [false]]);
});

it("is described by its description", () => {
  renderV1(<Switch label="Dark mode" description="Follows the system" />);
  const control = screen.getByRole("switch", { name: "Dark mode" });
  const description = screen.getByText("Follows the system");
  expect(description.id).not.toBe("");
  expect(control.getAttribute("aria-describedby")).toBe(description.id);
});

it("keeps the caller's aria-describedby alongside the description", () => {
  renderV1(
    <Switch
      label="Dark mode"
      description="Follows the system"
      aria-describedby="extra"
    />,
  );
  const control = screen.getByRole("switch", { name: "Dark mode" });
  const ids = control.getAttribute("aria-describedby")?.split(" ") ?? [];
  expect(ids).toContain("extra");
  expect(ids).toContain(screen.getByText("Follows the system").id);
});

it("does nothing when disabled", async () => {
  const onCheckedChange = vi.fn();
  const { user } = renderV1(
    <Switch label="Dark mode" disabled onCheckedChange={onCheckedChange} />,
  );
  const control = screen.getByRole("switch", { name: "Dark mode" });
  expect(control).toHaveAttribute("disabled");
  expect(screen.getByText("Dark mode")).toHaveAttribute("data-disabled");

  await user.click(screen.getByText("Dark mode"));
  control.focus();
  await user.keyboard(" ");
  expect(control).toHaveAttribute("aria-checked", "false");
  expect(onCheckedChange).not.toHaveBeenCalled();
});

it("is 20 by 36 by class", () => {
  renderV1(<Switch aria-label="Dark mode" />);
  const control = screen.getByRole("switch", { name: "Dark mode" });
  expect(control).toHaveClass("ui:h-5", "ui:w-9");
  const thumb = control.querySelector("[data-slot=switch-thumb]");
  expect(thumb).not.toBeNull();
  expect(thumb).toHaveClass("ui:size-4");
});

it("renders only the switch when there is no label or description", () => {
  const { container } = renderV1(<Switch aria-label="Dark mode" />);
  const row = container.querySelector("[data-slot=control-row]");
  expect(row).not.toBeNull();
  const control = screen.getByRole("switch", { name: "Dark mode" });
  expect(row?.children).toHaveLength(1);
  const wrapper = row?.firstElementChild;
  expect(wrapper?.tagName).toBe("SPAN");
  expect(wrapper?.children).toHaveLength(1);
  expect(wrapper?.firstElementChild).toBe(control);
  expect(control).not.toHaveAttribute("aria-describedby");
});

it("clicking the label toggles an enabled switch", async () => {
  const onCheckedChange = vi.fn();
  const { user } = renderV1(
    <Switch label="Dark mode" onCheckedChange={onCheckedChange} />,
  );
  const control = screen.getByRole("switch", { name: "Dark mode" });
  await user.click(screen.getByText("Dark mode"));
  expect(control).toHaveAttribute("aria-checked", "true");
  expect(onCheckedChange).toHaveBeenLastCalledWith(true);
  await user.click(screen.getByText("Dark mode"));
  expect(control).toHaveAttribute("aria-checked", "false");
  expect(onCheckedChange).toHaveBeenLastCalledWith(false);
});
