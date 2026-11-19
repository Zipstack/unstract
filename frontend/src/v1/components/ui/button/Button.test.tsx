import { screen } from "@testing-library/react";
import { ACTION_ICONS } from "@v1/lib/icons";
import { renderV1 } from "@v1/test";
import { createElement, createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { ButtonGroup } from "./ButtonGroup";

describe("Button", () => {
  it("activates on click, Enter and Space", async () => {
    const onClick = vi.fn();
    const { user } = renderV1(<Button onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });

    await user.click(button);
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(3);
  });

  it("is type button by default and passes its ref", () => {
    const ref = createRef<HTMLButtonElement>();
    renderV1(<Button ref={ref}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("type", "button");
    expect(ref.current).toBe(button);
  });

  it("ignores clicks and keys while loading but keeps focus", async () => {
    const onClick = vi.fn();
    const { user } = renderV1(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("aria-disabled", "true");

    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(button).toHaveFocus();
  });

  it("does not submit its form while loading", async () => {
    const onSubmit = vi.fn((event: SubmitEvent) => event.preventDefault());
    const { user } = renderV1(
      <form onSubmit={(event) => onSubmit(event.nativeEvent as SubmitEvent)}>
        <input aria-label="Name" />
        <Button type="submit" loading>
          Save
        </Button>
      </form>,
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.type(screen.getByRole("textbox", { name: "Name" }), "a{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("skips its own handlers and keeps a click from reaching a parent", async () => {
    const parent = vi.fn();
    const own = { onPointerDown: vi.fn(), onKeyDown: vi.fn() };
    // A stand-in for a clickable table row.
    const row = createElement(
      "div",
      { onClick: parent },
      <Button loading {...own}>
        Save
      </Button>,
    );
    const { user } = renderV1(row);
    const button = screen.getByRole("button", { name: "Save" });
    await user.click(button);
    await user.keyboard("{Enter}");
    expect(parent).not.toHaveBeenCalled();
    expect(own.onPointerDown).not.toHaveBeenCalled();
    expect(own.onKeyDown).not.toHaveBeenCalled();
  });

  it("shows a spinner while loading even without a leading icon", () => {
    const { container } = renderV1(<Button loading>Save</Button>);
    const svgs = container.querySelectorAll("svg");
    expect(svgs).toHaveLength(1);
    expect(svgs[0]).toHaveClass("lucide-loader-circle");
  });

  it("shows the spinner in place of the leading icon while loading", () => {
    const { container, rerender } = renderV1(
      <Button leadingIcon={ACTION_ICONS.add}>New</Button>,
    );
    expect(container.querySelector(".lucide-plus")).not.toBeNull();

    rerender(
      <Button leadingIcon={ACTION_ICONS.add} loading>
        New
      </Button>,
    );
    expect(container.querySelector(".lucide-plus")).toBeNull();
    const svgs = container.querySelectorAll("svg");
    expect(svgs).toHaveLength(1);
    expect(svgs[0]).toHaveClass("lucide-loader-circle");
    expect(svgs[0]).toHaveAttribute("aria-hidden", "true");
  });

  it("does not fire when disabled", async () => {
    const onClick = vi.fn();
    const { user } = renderV1(
      <Button disabled onClick={onClick}>
        Save
      </Button>,
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("ButtonGroup", () => {
  it("is a named group of its buttons", () => {
    renderV1(
      <ButtonGroup aria-label="Range">
        <Button variant="outline">Day</Button>
        <Button variant="outline">Week</Button>
      </ButtonGroup>,
    );
    const group = screen.getByRole("group", { name: "Range" });
    expect(group.querySelectorAll("button")).toHaveLength(2);
  });
});
