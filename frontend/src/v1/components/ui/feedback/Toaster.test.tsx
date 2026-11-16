import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  dismissNotification,
  NOTIFY_KINDS,
  notify,
  toast,
} from "@v1/lib/notify";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MAX_TOASTS, Toaster } from "./Toaster";

let container: HTMLElement;

beforeEach(() => {
  container = document.createElement("div");
  container.className = "v1";
  document.body.appendChild(container);
});

afterEach(() => {
  vi.useRealTimers();
  container.remove();
});

const mount = (duration?: number) =>
  render(<Toaster container={container} duration={duration} />);

const toasts = () => container.querySelectorAll("[data-slot=toast]");

it("shows a toast with its title, description and kind in the viewport", () => {
  mount();
  act(() => {
    notify({
      kind: "success",
      title: "Export started",
      description: "JSON soon",
    });
  });
  const [item] = toasts();
  expect(item?.textContent).toContain("Export started");
  expect(item?.textContent).toContain("JSON soon");
  expect(item?.getAttribute("data-kind")).toBe("success");
  expect(container.querySelector("ol")).not.toBeNull();
});

const announcer = (text: string) =>
  [...document.querySelectorAll("[role=status][aria-live]")].find((el) =>
    el.textContent?.includes(text),
  );

it("announces errors assertively and every other kind politely", async () => {
  mount();
  for (const kind of NOTIFY_KINDS) {
    let id: string | undefined;
    act(() => {
      id = notify({ kind, title: `Kind ${kind}`, persistent: true });
    });
    // Radix fills its announcers a frame after the toast mounts.
    await waitFor(() => {
      expect(announcer(`Kind ${kind}`)?.getAttribute("aria-live")).toBe(
        kind === "error" ? "assertive" : "polite",
      );
    });
    act(() => {
      toast.dismiss(id as string);
    });
  }
});

it("shows the request id where it can be copied", () => {
  mount();
  act(() => {
    toast.error("Could not save", { requestId: "req-42" });
  });
  const id = screen.getByText("Request ID: req-42");
  expect(id.className).toContain("ui:select-text");
});

it("closes after the timeout unless persistent", () => {
  vi.useFakeTimers();
  mount(1000);
  act(() => {
    toast.success("Gone soon");
    toast.warning("Stays", { persistent: true });
  });
  act(() => {
    vi.advanceTimersByTime(1500);
  });
  expect(screen.queryByText("Gone soon")).toBeNull();
  expect(screen.getByText("Stays")).not.toBeNull();
});

it("pauses the timeout while the pointer is over the toasts", () => {
  vi.useFakeTimers();
  mount(1000);
  act(() => {
    toast.success("Read me");
  });
  // Radix listens on the region around the list; pointerleave does not bubble.
  const region = screen.getByRole("region", { name: /Notifications/ });
  fireEvent.pointerMove(region);
  act(() => {
    vi.advanceTimersByTime(3000);
  });
  expect(screen.getByText("Read me")).not.toBeNull();
  fireEvent.pointerLeave(region);
  act(() => {
    vi.advanceTimersByTime(1500);
  });
  expect(screen.queryByText("Read me")).toBeNull();
});

it("runs the action and closes the toast", async () => {
  const user = userEvent.setup();
  const onSelect = vi.fn();
  mount();
  act(() => {
    toast.error("gpt-5.6 could not connect", {
      action: { label: "Edit profile", onSelect },
    });
  });
  await user.click(screen.getByRole("button", { name: "Edit profile" }));
  expect(onSelect).toHaveBeenCalledOnce();
  expect(onSelect.mock.calls[0]).toEqual([]);
  expect(screen.queryByText("gpt-5.6 could not connect")).toBeNull();
});

it("lets the keyboard reach an action toast through the F8 hotkey", async () => {
  const user = userEvent.setup();
  mount();
  act(() => {
    toast.info("Update ready", {
      action: { label: "Reload", onSelect: () => undefined },
      persistent: true,
    });
  });
  fireEvent.keyDown(document, { key: "F8", code: "F8" });
  expect(document.activeElement).toBe(container.querySelector("ol"));
  await user.tab();
  expect(document.activeElement).toBe(
    container.querySelector("[data-slot=toast]"),
  );
  await user.tab();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Reload" }),
  );
});

it("dismisses from the close button, by id, and with Escape", async () => {
  const user = userEvent.setup();
  mount();
  let id: string | undefined;
  act(() => {
    toast.info("One", { persistent: true });
    id = toast.info("Two", { persistent: true });
    toast.info("Three", { persistent: true });
  });
  await user.click(
    screen.getAllByRole("button", {
      name: "Dismiss notification",
    })[0] as HTMLElement,
  );
  expect(screen.queryByText("One")).toBeNull();
  act(() => {
    dismissNotification(id as string);
  });
  expect(screen.queryByText("Two")).toBeNull();
  (container.querySelector("[data-slot=toast]") as HTMLElement).focus();
  await user.keyboard("{Escape}");
  expect(screen.queryByText("Three")).toBeNull();
});

it("keeps at most MAX_TOASTS, dropping the oldest, and replaces by id", () => {
  mount();
  act(() => {
    for (let i = 1; i <= MAX_TOASTS + 1; i++) {
      toast.info(`Toast ${i}`, { persistent: true });
    }
  });
  expect(toasts()).toHaveLength(MAX_TOASTS);
  expect(screen.queryByText("Toast 1")).toBeNull();
  act(() => {
    notify({ kind: "info", title: "Uploading 1 of 2", id: "upload" });
  });
  const open = container.querySelector("[data-kind=info]:last-child");
  expect(open?.textContent).toContain("Uploading 1 of 2");
  act(() => {
    notify({ kind: "success", title: "Uploaded 2 of 2", id: "upload" });
  });
  expect(screen.queryByText("Uploading 1 of 2")).toBeNull();
  const replaced = screen
    .getByText("Uploaded 2 of 2")
    .closest("[data-slot=toast]");
  expect(replaced?.getAttribute("data-kind")).toBe("success");
  expect(toasts()).toHaveLength(MAX_TOASTS);
});

it("drops timed toasts before persistent ones at the limit", () => {
  mount();
  act(() => {
    toast.error("Upload failed", { persistent: true });
  });
  act(() => {
    for (let i = 1; i <= MAX_TOASTS; i++) {
      toast.success(`Saved ${i}`);
    }
  });
  expect(toasts()).toHaveLength(MAX_TOASTS);
  expect(screen.getByText("Upload failed")).not.toBeNull();
  expect(screen.queryByText("Saved 1")).toBeNull();
  expect(screen.getByText("Saved 3")).not.toBeNull();
});

it("gives a replacement its own timer and persistence", () => {
  vi.useFakeTimers();
  mount(1000);
  act(() => {
    notify({ kind: "info", title: "Uploading", id: "upload" });
  });
  act(() => {
    vi.advanceTimersByTime(900);
  });
  act(() => {
    notify({
      kind: "error",
      title: "Upload failed",
      id: "upload",
      persistent: true,
    });
  });
  act(() => {
    vi.advanceTimersByTime(5000);
  });
  expect(screen.getByText("Upload failed")).not.toBeNull();
  act(() => {
    notify({ kind: "success", title: "Uploaded", id: "upload" });
  });
  act(() => {
    vi.advanceTimersByTime(900);
  });
  // A fresh 1000ms timer, not the remains of an earlier one.
  expect(screen.getByText("Uploaded")).not.toBeNull();
  act(() => {
    vi.advanceTimersByTime(200);
  });
  expect(screen.queryByText("Uploaded")).toBeNull();
});

it("announces a replacement", async () => {
  mount();
  act(() => {
    notify({ kind: "info", title: "Uploading", id: "upload" });
  });
  await waitFor(() => expect(announcer("Uploading")).toBeDefined());
  act(() => {
    notify({ kind: "error", title: "Upload failed", id: "upload" });
  });
  await waitFor(() => {
    expect(announcer("Upload failed")?.getAttribute("aria-live")).toBe(
      "assertive",
    );
  });
});

it("keeps a replacement that the toast's own action sends", async () => {
  const user = userEvent.setup();
  mount();
  act(() => {
    toast.error("Upload failed", {
      id: "upload",
      persistent: true,
      action: {
        label: "Retry",
        onSelect: () => toast.info("Retrying", { id: "upload" }),
      },
    });
  });
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(screen.queryByText("Upload failed")).toBeNull();
  expect(screen.getByText("Retrying")).not.toBeNull();
});

it("moves focus to the viewport when a focused toast is removed", () => {
  mount();
  let id: string | undefined;
  act(() => {
    id = toast.info("Focused", { persistent: true });
  });
  (container.querySelector("[data-slot=toast]") as HTMLElement).focus();
  act(() => {
    dismissNotification(id as string);
  });
  expect(document.activeElement).toBe(container.querySelector("ol"));
});

it("leaves focus alone when a later timeout empties the list", () => {
  vi.useFakeTimers();
  mount(1000);
  const input = document.createElement("input");
  document.body.appendChild(input);
  let id: string | undefined;
  act(() => {
    id = toast.info("Focused", { persistent: true });
    toast.info("Timed");
  });
  (container.querySelector("[data-slot=toast]") as HTMLElement).focus();
  act(() => {
    dismissNotification(id as string);
  });
  input.focus();
  act(() => {
    vi.advanceTimersByTime(1500);
  });
  expect(screen.queryByText("Timed")).toBeNull();
  expect(document.activeElement).toBe(input);
  input.remove();
});

it("times out the next toast after the last one closes under the pointer", () => {
  vi.useFakeTimers();
  mount(1000);
  act(() => {
    toast.info("First", { persistent: true });
  });
  fireEvent.pointerMove(screen.getByRole("region", { name: /Notifications/ }));
  fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
  expect(screen.queryByText("First")).toBeNull();
  act(() => {
    toast.info("Second");
  });
  act(() => {
    vi.advanceTimersByTime(1500);
  });
  expect(screen.queryByText("Second")).toBeNull();
});

it("follows a new container", () => {
  const other = document.createElement("div");
  document.body.appendChild(other);
  const { rerender } = render(<Toaster container={container} />);
  rerender(<Toaster container={other} />);
  act(() => {
    toast.info("Moved", { persistent: true });
  });
  expect(other.querySelector("[data-slot=toast]")?.textContent).toContain(
    "Moved",
  );
  expect(container.querySelector("[data-slot=toast]")).toBeNull();
  other.remove();
});

it("stops receiving notifications once unmounted", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { unmount } = mount();
  unmount();
  expect(toast.error("After unmount")).toBeUndefined();
  expect(error).toHaveBeenCalled();
  error.mockRestore();
});

it("renders into the v1 portal container by default", () => {
  render(<Toaster />);
  act(() => {
    toast.success("Portalled");
  });
  const portal = document.getElementById("v1-portal");
  expect(portal?.classList.contains("v1")).toBe(true);
  expect(portal?.querySelector("[data-slot=toast]")?.textContent).toContain(
    "Portalled",
  );
});
