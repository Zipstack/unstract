import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { Checkbox } from "./Checkbox";

it("renders a checkbox named by its label and described by its description", () => {
  renderV1(<Checkbox label="Email me" description="Weekly digest" />);
  const box = screen.getByRole("checkbox", { name: "Email me" });
  const description = screen.getByText("Weekly digest");
  expect(description.id).not.toBe("");
  expect(box.getAttribute("aria-describedby")).toBe(description.id);
});

it("toggles with a click on the box and on the label, and with Space", async () => {
  const onCheckedChange = vi.fn();
  const { user } = renderV1(
    <Checkbox label="Email me" onCheckedChange={onCheckedChange} />,
  );
  const box = screen.getByRole("checkbox", { name: "Email me" });
  expect(box).toHaveAttribute("aria-checked", "false");

  await user.click(screen.getByText("Email me"));
  expect(box).toHaveAttribute("aria-checked", "true");
  expect(onCheckedChange).toHaveBeenLastCalledWith(true);

  await user.click(box);
  expect(box).toHaveAttribute("aria-checked", "false");
  expect(onCheckedChange).toHaveBeenLastCalledWith(false);

  await user.click(box);
  expect(box).toHaveAttribute("aria-checked", "true");
  box.focus();
  await user.keyboard(" ");
  expect(box).toHaveAttribute("aria-checked", "false");
  expect(onCheckedChange).toHaveBeenLastCalledWith(false);
});

it("shows a minus and reports mixed when indeterminate, and Space makes it checked", async () => {
  const onCheckedChange = vi.fn();
  const { user } = renderV1(
    <Checkbox
      label="All rows"
      checked="indeterminate"
      onCheckedChange={onCheckedChange}
    />,
  );
  const box = screen.getByRole("checkbox", { name: "All rows" });
  expect(box).toHaveAttribute("aria-checked", "mixed");
  expect(box.querySelector("svg.lucide-minus")).not.toBeNull();
  expect(box.querySelector("svg.lucide-check")).toBeNull();

  box.focus();
  await user.keyboard(" ");
  expect(onCheckedChange).toHaveBeenCalledWith(true);
});

it("does nothing when disabled", async () => {
  const onCheckedChange = vi.fn();
  const { user } = renderV1(
    <Checkbox label="Email me" disabled onCheckedChange={onCheckedChange} />,
  );
  const box = screen.getByRole("checkbox", { name: "Email me" });
  expect(box).toHaveAttribute("disabled");
  expect(screen.getByText("Email me")).toHaveAttribute("data-disabled");

  await user.click(screen.getByText("Email me"));
  box.focus();
  await user.keyboard(" ");
  expect(box).toHaveAttribute("aria-checked", "false");
  expect(onCheckedChange).not.toHaveBeenCalled();
});

it("keeps the caller's aria-describedby alongside the description", () => {
  renderV1(
    <Checkbox
      label="Email me"
      description="Weekly digest"
      aria-describedby="extra"
    />,
  );
  const box = screen.getByRole("checkbox", { name: "Email me" });
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  expect(ids).toContain("extra");
  expect(ids).toContain(screen.getByText("Weekly digest").id);
});

it("renders only the box when there is no label or description", () => {
  const { container } = renderV1(<Checkbox aria-label="Select row" />);
  const row = container.querySelector("[data-slot=control-row]");
  expect(row).not.toBeNull();
  const box = screen.getByRole("checkbox", { name: "Select row" });
  expect(row?.children).toHaveLength(1);
  expect(row?.firstElementChild).toBe(box);
  expect(box).not.toHaveAttribute("aria-describedby");
  expect(row?.querySelector("[data-slot=control-label]")).toBeNull();
  expect(row?.querySelector("p")).toBeNull();
});
