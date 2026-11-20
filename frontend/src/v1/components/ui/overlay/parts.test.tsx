import { screen } from "@testing-library/react";
import { Button } from "@v1/components/ui/button";
import { SearchField } from "@v1/components/ui/form";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  MenuButton,
} from "@v1/components/ui/menu";
import { getPortalContainer } from "@v1/lib/portal";
import { renderV1 } from "@v1/test";
import { Dialog as RadixDialog } from "radix-ui";
import { type ReactNode, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  type DismissHandlers,
  dismissGuards,
  OVERLAY_SCRIM,
  OverlayFooter,
  OverlayHeader,
  useReturnFocus,
} from "./parts";

type PanelProps = Readonly<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy?: boolean;
  own?: DismissHandlers;
  children?: ReactNode;
}>;

/** A Radix dialog built from the shared parts, as the drawer and dialogs are. */
function Panel({ open, onOpenChange, busy, own, children }: PanelProps) {
  const onCloseAutoFocus = useReturnFocus(open);
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal container={getPortalContainer()}>
        <div data-testid="scrim" className={OVERLAY_SCRIM} />
        <RadixDialog.Content
          {...dismissGuards(busy, own)}
          onCloseAutoFocus={onCloseAutoFocus}
        >
          <OverlayHeader
            title="health-monitoring API"
            description="API deployment · owner ritwik"
            busy={busy}
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

  it("ignores a click on a toast", async () => {
    const { user } = renderV1(
      <>
        <OpenedByButton />
        <div data-slot="toast">
          <button type="button">Undo</button>
        </div>
      </>,
      OUTSIDE,
    );
    await user.click(
      screen.getByRole("button", { name: "Undo", hidden: true }),
    );
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
});
