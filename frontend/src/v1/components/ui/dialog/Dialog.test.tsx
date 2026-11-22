import { screen, waitFor } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { Button } from "@v1/components/ui/button";
import { Field, Input, SearchField } from "@v1/components/ui/form";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  MenuButton,
} from "@v1/components/ui/menu";
import { renderV1 } from "@v1/test";
import { type ReactNode, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ANSWER_GUARD_MS, ConfirmHost } from "./ConfirmHost";
import { confirm } from "./confirm";
import {
  Dialog,
  DialogBody,
  DialogCancel,
  DialogContent,
  DialogFooter,
  DialogHeader,
  type DialogProps,
  DialogTrigger,
} from "./Dialog";

// A modal dialog sets pointer-events: none on <body>; clicks outside still reach the document.
const OUTSIDE = { userEventOptions: { pointerEventsCheck: 0 } } as const;

type SampleProps = Omit<DialogProps, "children"> &
  Readonly<{ children?: ReactNode; cancelFirst?: boolean }>;

function Sample({ children, cancelFirst, ...props }: SampleProps) {
  return (
    <Dialog {...props}>
      <DialogTrigger asChild>
        <Button>Open</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader
          title="New API deployment"
          description="Turns a workflow into an endpoint."
        />
        <DialogBody>{children}</DialogBody>
        <DialogFooter>
          <DialogCancel data-autofocus={cancelFirst || undefined} />
          <Button size="lg">Create</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

async function openSample(ui: ReactNode) {
  const result = renderV1(ui, OUTSIDE);
  const trigger = screen.getByRole("button", { name: "Open" });
  await result.user.click(trigger);
  return { ...result, trigger };
}

const scrim = () =>
  document.querySelector<HTMLElement>("[data-slot=dialog-scrim]");

const CLOSE_PATHS: Record<string, (user: UserEvent) => Promise<void>> = {
  Escape: (user) => user.keyboard("{Escape}"),
  "the close button": (user) =>
    user.click(screen.getByRole("button", { name: "Close" })),
  Cancel: (user) => user.click(screen.getByRole("button", { name: "Cancel" })),
  "an outside click": async (user) => {
    const element = scrim();
    if (element) {
      await user.click(element);
    }
  },
};

describe("Dialog", () => {
  it("is named by its title and described by its description", async () => {
    await openSample(<Sample />);
    const dialog = screen.getByRole("dialog", { name: "New API deployment" });
    expect(dialog).toHaveAccessibleDescription(
      "Turns a workflow into an endpoint.",
    );
  });

  it.each(
    Object.keys(CLOSE_PATHS),
  )("closes on %s and returns focus to the trigger", async (path) => {
    const { user, trigger } = await openSample(<Sample />);
    await CLOSE_PATHS[path](user);
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("stays open on an outside click when not dismissible, but Escape closes it", async () => {
    const { user } = await openSample(<Sample dismissible={false} />);
    await CLOSE_PATHS["an outside click"](user);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("ignores every close path while busy and disables Close and Cancel", async () => {
    const { user } = await openSample(<Sample busy />);
    for (const close of Object.values(CLOSE_PATHS)) {
      await close(user);
    }
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("asks beforeClose on every close path and stays open on no", async () => {
    const beforeClose = vi.fn(() => false);
    const { user } = await openSample(<Sample beforeClose={beforeClose} />);
    for (const close of Object.values(CLOSE_PATHS)) {
      await close(user);
    }
    expect(beforeClose).toHaveBeenCalledTimes(4);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    beforeClose.mockReturnValue(true);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("focuses the body's first field when it opens", async () => {
    await openSample(
      <Sample>
        <Field id="t-name" label="Display name">
          <Input />
        </Field>
      </Sample>,
    );
    expect(screen.getByRole("textbox", { name: "Display name" })).toHaveFocus();
  });

  it("focuses the control marked data-autofocus first", async () => {
    await openSample(
      <Sample cancelFirst>
        <Field id="t-name" label="Display name">
          <Input />
        </Field>
      </Sample>,
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("lets a filled SearchField clear on Escape before closing", async () => {
    const { user } = await openSample(
      <Sample>
        <SearchField aria-label="Search keys" />
      </Sample>,
    );
    await user.type(screen.getByRole("searchbox"), "ci");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("searchbox")).toHaveValue("");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

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
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent aria-describedby={undefined}>
          <DialogHeader title="Edit deployment" />
        </DialogContent>
      </Dialog>
    </>
  );
}

it("returns focus to the menu's trigger when a menu item opened it", async () => {
  const { user } = renderV1(<OpenedFromMenu />);
  const trigger = screen.getByRole("button", { name: "Actions" });
  await user.click(trigger);
  await user.click(screen.getByRole("menuitem", { name: "Edit" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
});

describe("a dirty form guarded by confirm()", () => {
  // Only Date is faked, so the confirm's answer guard can be passed without waiting.
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const discard = () =>
    confirm({
      tone: "destructive",
      title: "Discard unsaved changes?",
      description: "Your edits to this deployment are not saved.",
      consequence: "They are lost when the dialog closes.",
      confirmLabel: "Discard",
    });

  async function openGuarded() {
    const opened = await openSample(
      <>
        <Sample beforeClose={discard} />
        <ConfirmHost />
      </>,
    );
    await opened.user.keyboard("{Escape}");
    await screen.findByRole("alertdialog", {
      name: "Discard unsaved changes?",
    });
    vi.setSystemTime(Date.now() + ANSWER_GUARD_MS);
    return opened;
  }

  it("closes both and returns focus to the trigger on Discard", async () => {
    const { user, trigger } = await openGuarded();
    await user.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("keeps the form open on Cancel", async () => {
    const { user } = await openGuarded();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("alertdialog", { name: "Discard unsaved changes?" }),
      ).toBeNull(),
    );
    expect(
      screen.getByRole("dialog", { name: "New API deployment" }),
    ).toBeInTheDocument();
  });
});
