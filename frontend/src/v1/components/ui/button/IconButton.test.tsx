import { screen } from "@testing-library/react";
import { ACTION_ICONS } from "@v1/lib/icons";
import { axeViolations, renderV1 } from "@v1/test";
import { Toggle } from "radix-ui";
import { expect, it, vi } from "vitest";
import { IconButton, type IconButtonProps } from "./IconButton";

it("is a button named by its aria-label", async () => {
  const onClick = vi.fn();
  const { user } = renderV1(
    <IconButton icon={ACTION_ICONS.edit} aria-label="Edit" onClick={onClick} />,
  );
  const button = screen.getByRole("button", { name: "Edit" });
  expect(button).toHaveAttribute("type", "button");
  await user.click(button);
  await user.keyboard("{Enter}");
  expect(onClick).toHaveBeenCalledTimes(2);
});

it("exposes selected as aria-pressed only when given", () => {
  const { rerender } = renderV1(
    <IconButton icon={ACTION_ICONS.filter} aria-label="Filter" />,
  );
  const button = screen.getByRole("button", { name: "Filter" });
  expect(button).not.toHaveAttribute("aria-pressed");

  rerender(
    <IconButton icon={ACTION_ICONS.filter} aria-label="Filter" selected />,
  );
  expect(button).toHaveAttribute("aria-pressed", "true");

  rerender(
    <IconButton
      icon={ACTION_ICONS.filter}
      aria-label="Filter"
      selected={false}
    />,
  );
  expect(button).toHaveAttribute("aria-pressed", "false");
});

it("keeps the aria-pressed a Radix Toggle gives it when selected is not set", async () => {
  const { user } = renderV1(
    <Toggle.Root asChild defaultPressed>
      <IconButton icon={ACTION_ICONS.filter} aria-label="Filter" />
    </Toggle.Root>,
  );
  const button = screen.getByRole("button", { name: "Filter" });
  expect(button).toHaveAttribute("aria-pressed", "true");
  await user.click(button);
  expect(button).toHaveAttribute("aria-pressed", "false");
});

it("looks the same pressed by selected or by a Radix Toggle", () => {
  renderV1(
    <>
      <IconButton icon={ACTION_ICONS.filter} aria-label="By prop" selected />
      <Toggle.Root asChild pressed>
        <IconButton icon={ACTION_ICONS.filter} aria-label="By Toggle" />
      </Toggle.Root>
    </>,
  );
  const byProp = screen.getByRole("button", { name: "By prop" });
  const byToggle = screen.getByRole("button", { name: "By Toggle" });
  expect(byToggle).toHaveAttribute("aria-pressed", "true");
  expect(byToggle.className).toBe(byProp.className);
  expect(byToggle).toHaveClass("ui:aria-pressed:bg-primary");
});

it("fails the accessibility scan without a name", async () => {
  const unnamed = { icon: ACTION_ICONS.edit } as IconButtonProps;
  const { container } = renderV1(<IconButton {...unnamed} />);
  const rules = (await axeViolations(container)).map(({ id }) => id);
  expect(rules).toContain("button-name");
});

// Type-level guard, never rendered: every icon button has a name.
export function _iconButtonNeedsAName() {
  return (
    <>
      <IconButton icon={ACTION_ICONS.edit} aria-label="x" />
      <IconButton icon={ACTION_ICONS.edit} aria-labelledby="x" />
      {/* @ts-expect-error an icon button needs aria-label or aria-labelledby */}
      <IconButton icon={ACTION_ICONS.edit} />
    </>
  );
}
