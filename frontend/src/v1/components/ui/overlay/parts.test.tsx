import { screen, waitFor } from "@testing-library/react";
import { Button } from "@v1/components/ui/button";
import { SearchField } from "@v1/components/ui/form";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
  MenuButton,
} from "@v1/components/ui/menu";
import { getPortalContainer } from "@v1/lib/portal";
import { renderV1 } from "@v1/test";
import { Dialog as RadixDialog } from "radix-ui";
import { type ReactNode, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Popover, PopoverContent, PopoverTrigger } from "./Popover";
import {
  type DismissHandlers,
  dismissGuards,
  OVERLAY_SCRIM,
  OverlayFooter,
  OverlayHeader,
  type OverlayHeaderProps,
} from "./parts";
import { useReturnFocus } from "./returnFocus";

type PanelProps = Readonly<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy?: boolean;
  titleSize?: OverlayHeaderProps["titleSize"];
  own?: DismissHandlers;
  children?: ReactNode;
}>;

/** A Radix dialog built from the shared parts, as the drawer and dialogs are. */
function Panel({ open, onOpenChange, own, children, ...header }: PanelProps) {
  const onCloseAutoFocus = useReturnFocus(open);
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal container={getPortalContainer()}>
        <div data-testid="scrim" className={OVERLAY_SCRIM} />
        <RadixDialog.Content
          {...dismissGuards(header.busy, own)}
          onCloseAutoFocus={onCloseAutoFocus}
        >
          <OverlayHeader
            title="health-monitoring API"
            description="API deployment · owner ritwik"
            {...header}
          />
          {children}
          <OverlayFooter>
            <Button>Done</Button>
          </OverlayFooter>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

function OpenedByButton(props: Omit<PanelProps, "open" | "onOpenChange">) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Details</Button>
      <Panel open={open} onOpenChange={setOpen} {...props} />
    </>
  );
}

function OpenedFromMenu() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <MenuButton>Actions</MenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => setOpen(true)}>
            Edit
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Panel open={open} onOpenChange={setOpen} />
    </>
  );
}

function OpenedFromSubmenu() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <MenuButton>Actions</MenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>More</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              <DropdownMenuItem onSelect={() => setOpen(true)}>
                Edit
              </DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>
      <Panel open={open} onOpenChange={setOpen} />
    </>
  );
}

function OpenedFromPopover() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button>Profile</Button>
        </PopoverTrigger>
        <PopoverContent title="test3">
          <Button onClick={() => setOpen(true)}>Edit profile</Button>
        </PopoverContent>
      </Popover>
      <Panel open={open} onOpenChange={setOpen} />
    </>
  );
}

/** One overlay whose "Continue" closes it and reopens it in the same task, as chained confirms do. */
function Chained() {
  const [open, setOpen] = useState(false);
  const reopen = () => {
    setOpen(false);
    void Promise.resolve().then(() => setOpen(true));
  };
  return (
    <>
      <Button onClick={() => setOpen(true)}>Start</Button>
      <Panel open={open} onOpenChange={setOpen}>
        <Button onClick={reopen}>Continue</Button>
      </Panel>
    </>
  );
}

/** Two overlays: "Continue" in the first closes it and opens the second in the same task. */
function TwoInARow() {
  const [first, setFirst] = useState(false);
  const [second, setSecond] = useState(false);
  const next = () => {
    setFirst(false);
    void Promise.resolve().then(() => setSecond(true));
  };
  return (
    <>
      <Button onClick={() => setFirst(true)}>Start</Button>
      <Panel open={first} onOpenChange={setFirst}>
        <Button onClick={next}>Continue</Button>
      </Panel>
      <Panel open={second} onOpenChange={setSecond} />
    </>
  );
}

/** A controlled popover whose button closes it and opens the overlay in one update, as SearchMenu does. */
function OpenedFromControlledPopover() {
  const [popover, setPopover] = useState(false);
  const [open, setOpen] = useState(false);
  const edit = () => {
    setPopover(false);
    setOpen(true);
  };
  return (
    <>
      <Popover open={popover} onOpenChange={setPopover}>
        <PopoverTrigger asChild>
          <Button>Profile</Button>
        </PopoverTrigger>
        <PopoverContent title="test3">
          <Button onClick={edit}>Edit profile</Button>
        </PopoverContent>
      </Popover>
      <Panel open={open} onOpenChange={setOpen} />
    </>
  );
}

// A modal Radix dialog sets pointer-events: none on <body>; clicks outside still reach the document.
const OUTSIDE = { userEventOptions: { pointerEventsCheck: 0 } } as const;

describe("OverlayHeader and OverlayFooter", () => {
  it("names and describes the dialog, and its close button closes it", async () => {
    const { user } = renderV1(<OpenedByButton />);
    const dialog = screen.getByRole("dialog", {
      name: "health-monitoring API",
    });
    expect(dialog).toHaveAccessibleDescription("API deployment · owner ritwik");
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("sets the title at page size by default and section size on request", () => {
    const { unmount } = renderV1(<OpenedByButton />);
    const title = () =>
      screen.getByRole("heading", { name: "health-monitoring API" });
    expect(title()).toHaveClass("ui:text-page-title");
    expect(title()).not.toHaveClass("ui:text-section-title");
    unmount();
    renderV1(<OpenedByButton titleSize="section" />);
    expect(title()).toHaveClass("ui:text-section-title");
    expect(title()).not.toHaveClass("ui:text-page-title");
  });

  it("disables the close button while busy", () => {
    renderV1(<OpenedByButton busy />);
    expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
  });

  it("aligns the footer to the end unless asked to start", () => {
    const { rerender } = renderV1(<OverlayFooter data-testid="footer" />);
    expect(screen.getByTestId("footer")).toHaveClass("ui:justify-end");
    rerender(<OverlayFooter data-testid="footer" align="start" />);
    expect(screen.getByTestId("footer")).not.toHaveClass("ui:justify-end");
  });
});

describe("dismissGuards", () => {
  it("closes on Escape and on a click outside", async () => {
    const { user } = renderV1(<OpenedByButton />, OUTSIDE);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Details" }));
    await user.click(screen.getByTestId("scrim"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("clears a filled SearchField on the first Escape and closes on the next", async () => {
    const { user } = renderV1(
      <OpenedByButton>
        <SearchField aria-label="Search keys" />
      </OpenedByButton>,
    );
    const field = screen.getByRole("searchbox", { name: "Search keys" });
    await user.type(field, "ci");
    await user.keyboard("{Escape}");
    expect(field).toHaveValue("");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the overlay open while busy", async () => {
    const { user } = renderV1(<OpenedByButton busy />, OUTSIDE);
    await user.keyboard("{Escape}");
    await user.click(screen.getByTestId("scrim"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("runs the caller's handlers first, which may keep it open", async () => {
    const onEscapeKeyDown = vi.fn((event: KeyboardEvent) =>
      event.preventDefault(),
    );
    const { user } = renderV1(<OpenedByButton own={{ onEscapeKeyDown }} />);
    await user.keyboard("{Escape}");
    expect(onEscapeKeyDown).toHaveBeenCalledOnce();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("useReturnFocus", () => {
  it("returns focus to the button that opened the overlay", async () => {
    const { user } = renderV1(<OpenedByButton />);
    await user.keyboard("{Escape}");
    const opener = screen.getByRole("button", { name: "Details" });
    await user.click(opener);
    await user.keyboard("{Escape}");
    expect(opener).toHaveFocus();
  });

  it("returns focus to the menu's trigger when a menu item opened it", async () => {
    const { user } = renderV1(<OpenedFromMenu />);
    const trigger = screen.getByRole("button", { name: "Actions" });
    await user.click(trigger);
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem")).toBeNull();

    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });

  it("returns focus to the menu's trigger after a keyboard selection too", async () => {
    const { user } = renderV1(<OpenedFromMenu />);
    const trigger = screen.getByRole("button", { name: "Actions" });
    trigger.focus();
    await user.keyboard("{Enter}");
    await user.keyboard("{Enter}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });

  it("returns focus to the root menu's trigger when a submenu item opened it", async () => {
    const { user } = renderV1(<OpenedFromSubmenu />);
    const trigger = screen.getByRole("button", { name: "Actions" });
    trigger.focus();
    await user.keyboard("{Enter}");
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("menuitem", { name: "Edit" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem")).toBeNull();

    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });

  it("returns focus to the first opener when an overlay closes and reopens in the same task", async () => {
    const { user } = renderV1(<Chained />);
    const start = screen.getByRole("button", { name: "Start" });
    await user.click(start);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Close" })).toHaveFocus(),
    );
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(start).toHaveFocus();
  });

  it("returns focus to the first opener when one overlay closes and another opens in the same task", async () => {
    const { user } = renderV1(<TwoInARow />);
    const start = screen.getByRole("button", { name: "Start" });
    await user.click(start);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Close" })).toHaveFocus(),
    );
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(start).toHaveFocus();
  });

  it("returns focus to a controlled popover's trigger that closed as the overlay opened", async () => {
    const { user } = renderV1(<OpenedFromControlledPopover />);
    const trigger = screen.getByRole("button", { name: "Profile" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Edit profile" }));
    expect(screen.queryByRole("dialog", { name: "test3" })).toBeNull();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("returns focus to the popover's trigger when a button in the popover opened it", async () => {
    const { user } = renderV1(<OpenedFromPopover />);
    const trigger = screen.getByRole("button", { name: "Profile" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Edit profile" }));
    expect(
      screen.getByRole("dialog", { name: "health-monitoring API" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "test3" })).toBeNull();

    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });
});
