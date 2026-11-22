import { act, screen } from "@testing-library/react";
import { Button } from "@v1/components/ui/button";
import { Toaster } from "@v1/components/ui/feedback";
import { toast } from "@v1/lib/notify";
import { renderV1, type V1Harness } from "@v1/test";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Drawer, type DrawerProps, DrawerSection } from "./Drawer";

function DetailDrawer(props: Partial<DrawerProps>) {
  return (
    <Drawer
      trigger={<Button>Details</Button>}
      title="health-monitoring API"
      description="API deployment · owner ritwik"
      actions={
        <>
          <Button>View logs</Button>
          <Button variant="outline">Postman</Button>
        </>
      }
      {...props}
    >
      <DrawerSection title="Last 5 runs" meta="all five succeeded">
        <a href="#runs">Open runs</a>
      </DrawerSection>
    </Drawer>
  );
}

/** A drawer a plain control opens, as a list row does. */
function RowDrawer() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Open row</Button>
      <Drawer open={open} onOpenChange={setOpen} title="Row detail">
        <p>Detail</p>
      </Drawer>
    </>
  );
}

type User = V1Harness["user"];

const scrim = () =>
  document.querySelector<HTMLElement>(
    "[data-slot=drawer-scrim]",
  ) as HTMLElement;

// A modal Radix dialog sets pointer-events: none on <body>; clicks outside still reach the document.
const OUTSIDE = { userEventOptions: { pointerEventsCheck: 0 } } as const;

async function openDrawer(props: Partial<DrawerProps> = {}) {
  const harness = renderV1(<DetailDrawer {...props} />, OUTSIDE);
  const trigger = screen.getByRole("button", { name: "Details" });
  await harness.user.click(trigger);
  return { ...harness, trigger };
}

describe("Drawer", () => {
  it("opens as a named, described dialog with its sections and actions", async () => {
    await openDrawer();
    const drawer = screen.getByRole("dialog", {
      name: "health-monitoring API",
    });
    expect(drawer).toHaveAccessibleDescription("API deployment · owner ritwik");
    expect(
      screen.getByRole("heading", { level: 3, name: "Last 5 runs" }),
    ).toBeInTheDocument();
    expect(screen.getByText("all five succeeded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View logs" })).toBeVisible();
  });

  it("traps focus: Tab cycles inside the drawer", async () => {
    const { user } = await openDrawer();
    const close = screen.getByRole("button", { name: "Close" });
    expect(close).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Open runs" })).toHaveFocus();
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Postman" })).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Postman" })).toHaveFocus();
  });

  it.each<[string, (user: User) => Promise<void>]>([
    ["Escape", (user) => user.keyboard("{Escape}")],
    [
      "the close button",
      (user) => user.click(screen.getByRole("button", { name: "Close" })),
    ],
    ["a click on the dim layer", (user) => user.click(scrim())],
  ])("closes on %s and returns focus to the trigger", async (_how, close) => {
    const { user, trigger } = await openDrawer();
    await close(user);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("does not lock page scroll", async () => {
    await openDrawer();
    expect(document.body).not.toHaveAttribute("data-scroll-locked");
    expect(document.body.style.overflow).toBe("");
  });

  it("is 480 wide by default", async () => {
    await openDrawer();
    expect(screen.getByRole("dialog")).toHaveClass("ui:w-120");
  });

  it("is 640 wide at lg", async () => {
    await openDrawer({ size: "lg" });
    expect(screen.getByRole("dialog")).toHaveClass("ui:w-160");
  });

  it("stays open while busy", async () => {
    const { user } = await openDrawer({ busy: true });
    await user.keyboard("{Escape}");
    await user.click(scrim());
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
  });

  it("has no description when none is given", async () => {
    await openDrawer({ description: undefined });
    expect(screen.getByRole("dialog")).not.toHaveAttribute("aria-describedby");
  });

  it("is controlled through open and onOpenChange, without a trigger", async () => {
    const onOpenChange = vi.fn();
    const { user } = renderV1(
      <DetailDrawer trigger={undefined} open onOpenChange={onOpenChange} />,
    );
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows a leading logo and a badge in the header", async () => {
    await openDrawer({
      leading: <span data-testid="logo" />,
      badge: <span>Success</span>,
    });
    expect(screen.getByTestId("logo")).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
  });

  it("leaves out the action bar when there are no actions", async () => {
    await openDrawer({ actions: undefined });
    expect(document.querySelector("[data-slot=overlay-footer]")).toBeNull();
  });

  it("returns focus to the control that opened it without a trigger", async () => {
    const { user } = renderV1(<RowDrawer />);
    const row = screen.getByRole("button", { name: "Open row" });
    await user.click(row);
    expect(screen.getByRole("dialog", { name: "Row detail" })).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(row).toHaveFocus();
  });

  it("reports opening and closing when uncontrolled", async () => {
    const onOpenChange = vi.fn();
    const { user } = await openDrawer({ onOpenChange });
    expect(onOpenChange).toHaveBeenLastCalledWith(true);
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });

  it("keeps a toast raised while open above it, clickable, and first to close on Escape", async () => {
    const harness = renderV1(
      <>
        <Toaster />
        <DetailDrawer />
      </>,
      OUTSIDE,
    );
    const { user } = harness;
    await user.click(screen.getByRole("button", { name: "Details" }));
    act(() => {
      toast.error("Save failed");
    });
    const viewport = screen.getByText("Save failed").closest("ol");
    expect(viewport).toHaveClass("ui:z-60");
    expect(scrim()).toHaveClass("ui:z-50");

    const dismiss = { name: "Dismiss notification", hidden: true };
    await user.click(screen.getByRole("button", dismiss));
    expect(screen.queryByText("Save failed")).toBeNull();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    act(() => {
      toast.error("Save failed again");
    });
    await user.keyboard("{Escape}");
    expect(screen.queryByText("Save failed again")).toBeNull();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("takes text only as its title", () => {
    // @ts-expect-error a drawer's title is text, so a loading value cannot leave it unnamed
    const untitled = <Drawer title={undefined}>x</Drawer>;
    expect(untitled).toBeTruthy();
  });
});
