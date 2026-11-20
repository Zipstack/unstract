import { screen, waitFor } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { Button } from "@v1/components/ui/button";
import { renderV1 } from "@v1/test";
import { describe, expect, it, vi } from "vitest";
import { ConfirmHost } from "./ConfirmHost";
import { type ConfirmOptions, confirm } from "./confirm";

// A modal dialog sets pointer-events: none on <body>; clicks outside still reach the document.
const OUTSIDE = { userEventOptions: { pointerEventsCheck: 0 } } as const;

const STANDARD: ConfirmOptions = {
  title: "Regenerate the API key?",
  description: "The current key stops working.",
  confirmLabel: "Regenerate key",
};

const DESTRUCTIVE: ConfirmOptions = {
  tone: "destructive",
  title: "Delete “Invoice API”?",
  description: "The endpoint stops responding immediately.",
  consequence: "This cannot be undone.",
  confirmLabel: "Delete deployment",
};

/** Renders the host and an opener that asks every request in one click. */
function setup(...requests: ConfirmOptions[]) {
  const answers: boolean[] = [];
  const ask = () => {
    for (const options of requests) {
      void confirm(options).then((ok) => answers.push(ok));
    }
  };
  const result = renderV1(
    <>
      <Button onClick={ask}>Ask</Button>
      <ConfirmHost />
    </>,
    OUTSIDE,
  );
  const opener = screen.getByRole("button", { name: "Ask" });
  return { ...result, answers, opener };
}

async function ask(user: UserEvent, opener: HTMLElement, title: string) {
  await user.click(opener);
  return screen.findByRole("dialog", { name: title });
}

const scrim = () =>
  document.querySelector<HTMLElement>("[data-slot=dialog-scrim]");

describe("ConfirmHost", () => {
  it("resolves true on the action button and returns focus to the opener", async () => {
    const { user, opener, answers } = setup(STANDARD);
    await ask(user, opener, STANDARD.title);
    expect(
      screen.getByRole("button", { name: "Regenerate key" }),
    ).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Regenerate key" }));
    await waitFor(() => expect(answers).toEqual([true]));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it.each([
    ["Cancel", (user: UserEvent) => user.click(screen.getByText("Cancel"))],
    ["Escape", (user: UserEvent) => user.keyboard("{Escape}")],
    [
      "an outside click",
      (user: UserEvent) => user.click(scrim() as HTMLElement),
    ],
  ])("resolves false on %s", async (_path, close) => {
    const { user, opener, answers } = setup(STANDARD);
    await ask(user, opener, STANDARD.title);
    await close(user);
    await waitFor(() => expect(answers).toEqual([false]));
  });

  it("states the consequence, starts on Cancel and ignores an outside click when destructive", async () => {
    const { user, opener } = setup(DESTRUCTIVE);
    const dialog = await ask(user, opener, DESTRUCTIVE.title);
    expect(dialog).toHaveAccessibleDescription(
      "The endpoint stops responding immediately. This cannot be undone.",
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.click(scrim() as HTMLElement);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("offers only Close and the link when blocked, and resolves false", async () => {
    const onSelect = vi.fn();
    const { user, opener, answers } = setup({
      tone: "blocked",
      title: "Invoice Vendor Lookup cannot be deleted",
      reason: "Unlink it from its project first.",
      link: { label: "Open project", onSelect },
    });
    await ask(user, opener, "Invoice Vendor Lookup cannot be deleted");
    const footer = screen.getByRole("button", {
      name: "Open project",
    }).parentElement;
    expect(footer?.querySelectorAll("button")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Close" })[1]).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Open project" }));
    await waitFor(() => expect(answers).toEqual([false]));
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it("stays busy while the action runs, then resolves true", async () => {
    let finish: () => void = () => undefined;
    const action = () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      });
    const { user, opener, answers } = setup({ ...DESTRUCTIVE, action });
    await ask(user, opener, DESTRUCTIVE.title);
    const button = screen.getByRole("button", { name: "Delete deployment" });
    await user.click(button);
    expect(button).toHaveAttribute("aria-busy", "true");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    finish();
    await waitFor(() => expect(answers).toEqual([true]));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("stays open and logs when the action fails", async () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const action = () => Promise.reject(new Error("409"));
    const { user, opener, answers } = setup({ ...DESTRUCTIVE, action });
    await ask(user, opener, DESTRUCTIVE.title);
    await user.click(screen.getByRole("button", { name: "Delete deployment" }));
    await waitFor(() => expect(error).toHaveBeenCalledOnce());
    const button = screen.getByRole("button", { name: "Delete deployment" });
    expect(button).not.toHaveAttribute("aria-busy");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(answers).toEqual([false]));
  });

  it("shows a queued request next, focuses its default button, then returns focus", async () => {
    const { user, opener, answers } = setup(STANDARD, DESTRUCTIVE);
    await ask(user, opener, STANDARD.title);
    await user.click(screen.getByRole("button", { name: "Regenerate key" }));
    await screen.findByRole("dialog", { name: DESTRUCTIVE.title });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus(),
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(answers).toEqual([true, false]));
    await waitFor(() => expect(opener).toHaveFocus());
  });
});
