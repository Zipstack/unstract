import { act, screen } from "@testing-library/react";
import { Button, IconButton } from "@v1/components/ui/button";
import { SearchField } from "@v1/components/ui/form";
import { STATUS_ICONS } from "@v1/lib/icons";
import { renderV1 } from "@v1/test";
import { describe, expect, it, vi } from "vitest";
import { Popover, PopoverContent, PopoverTrigger } from "./Popover";

function ProfilePopover({ busy }: { busy?: boolean }) {
  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <IconButton aria-label="Profile" icon={STATUS_ICONS.info} />
        </PopoverTrigger>
        <PopoverContent
          title="test3"
          description="LLM profile used by this model column"
          busy={busy}
        >
          <SearchField aria-label="Filter settings" />
          <Button>Edit profile</Button>
        </PopoverContent>
      </Popover>
      <Button>Elsewhere</Button>
    </>
  );
}

async function openPopover(busy?: boolean) {
  const harness = renderV1(<ProfilePopover busy={busy} />);
  const trigger = screen.getByRole("button", { name: "Profile" });
  await harness.user.click(trigger);
  return { ...harness, trigger };
}

describe("Popover", () => {
  it("opens as a named, described dialog with focus inside", async () => {
    await openPopover();
    const popover = screen.getByRole("dialog", { name: "test3" });
    expect(popover).toHaveAccessibleDescription(
      "LLM profile used by this model column",
    );
    expect(popover).toContainElement(document.activeElement as HTMLElement);
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const { user, trigger } = await openPopover();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("closes on a click outside", async () => {
    const { user } = await openPopover();
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not trap focus: focus moving outside closes it and stays there", async () => {
    const { user } = await openPopover();
    expect(screen.getByRole("searchbox")).toHaveFocus();
    // Tab cycles inside, as Radix loops it.
    await user.tab();
    expect(screen.getByRole("button", { name: "Edit profile" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("searchbox")).toHaveFocus();

    const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
    act(() => elsewhere.focus());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(elsewhere).toHaveFocus();
  });

  it("clears a filled search on the first Escape", async () => {
    const { user } = await openPopover();
    await user.type(screen.getByRole("searchbox"), "chunk");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("stays open while busy", async () => {
    const { user } = await openPopover(true);
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("takes an aria-label when it has no visible title", async () => {
    const { user } = renderV1(
      <Popover>
        <PopoverTrigger asChild>
          <Button>Columns</Button>
        </PopoverTrigger>
        <PopoverContent aria-label="Choose columns">
          <Button>Reset</Button>
        </PopoverContent>
      </Popover>,
    );
    await user.click(screen.getByRole("button", { name: "Columns" }));
    expect(
      screen.getByRole("dialog", { name: "Choose columns" }),
    ).not.toHaveAttribute("aria-describedby");
  });

  it("runs the caller's Escape handler, which may keep it open", async () => {
    const onEscapeKeyDown = vi.fn((event: KeyboardEvent) =>
      event.preventDefault(),
    );
    const { user } = renderV1(
      <Popover defaultOpen>
        <PopoverTrigger asChild>
          <Button>Columns</Button>
        </PopoverTrigger>
        <PopoverContent
          aria-label="Choose columns"
          onEscapeKeyDown={onEscapeKeyDown}
        >
          <Button>Reset</Button>
        </PopoverContent>
      </Popover>,
    );
    await user.keyboard("{Escape}");
    expect(onEscapeKeyDown).toHaveBeenCalledOnce();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("takes no asChild or forceMount on its content", () => {
    // @ts-expect-error the content always renders its heading and children
    const slotted = <PopoverContent title="x" asChild />;
    // @ts-expect-error the content renders through its own portal
    const forced = <PopoverContent title="x" forceMount />;
    expect([slotted, forced]).toHaveLength(2);
  });

  it("requires a name", () => {
    // @ts-expect-error a popover needs a title or an aria-label
    const nameless = <PopoverContent>x</PopoverContent>;
    expect(nameless).toBeTruthy();
  });
});
