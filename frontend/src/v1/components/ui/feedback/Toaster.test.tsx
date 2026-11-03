import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { dismissNotification, notify, toast } from "@v1/lib/notify";
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

it("announces errors assertively and everything else politely", async () => {
  mount();
  act(() => {
    toast.error("Could not connect");
    toast.info("Heads up");
  });
  const live = (text: string) =>
    [...document.querySelectorAll("[role=status][aria-live]")].find((el) =>
      el.textContent?.includes(text),
    );
  // Radix fills its announcers a frame after the toast mounts.
  await waitFor(() => {
    expect(live("Could not connect")?.getAttribute("aria-live")).toBe(
      "assertive",
    );
    expect(live("Heads up")?.getAttribute("aria-live")).toBe("polite");
  });
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
    notify({ kind: "success", title: "Uploaded 2 of 2", id: "upload" });
  });
  expect(screen.queryByText("Uploading 1 of 2")).toBeNull();
  expect(screen.getByText("Uploaded 2 of 2")).not.toBeNull();
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
