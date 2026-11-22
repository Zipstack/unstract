import { act, screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { Button } from "@v1/components/ui/button";
import { renderV1 } from "@v1/test";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ANSWER_GUARD_MS, ConfirmHost } from "./ConfirmHost";
import { type ConfirmOptions, confirm } from "./confirm";

// A modal dialog sets pointer-events: none on <body>; clicks outside still reach the document.
const OUTSIDE = { userEventOptions: { pointerEventsCheck: 0 } } as const;

// Only Date is faked, so the answer guard can be passed without waiting.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
});
afterEach(() => {
  vi.useRealTimers();
});
const passGuard = () => vi.setSystemTime(Date.now() + ANSWER_GUARD_MS);

const STANDARD: ConfirmOptions = {
  title: "Regenerate the API key?",
  description: "The current key stops working.",
  confirmLabel: "Regenerate key",
};

const SECOND: ConfirmOptions = {
  ...STANDARD,
  title: "Regenerate the next key?",
};

const DESTRUCTIVE: ConfirmOptions = {
  tone: "destructive",
  title: "Delete “Invoice API”?",
  description: "The endpoint stops responding immediately.",
  consequence: "This cannot be undone.",
  confirmLabel: "Delete deployment",
};

const blocked = (onSelect: () => void): ConfirmOptions => ({
  tone: "blocked",
  title: "Invoice Vendor Lookup cannot be deleted",
  reason: "Unlink it from its project first.",
  link: { label: "Open project", onSelect },
});

/** Renders the host and an opener that asks every request in one click. */
function setup(...requests: ConfirmOptions[]) {
  const answers: boolean[] = [];
  const onAsk = () => {
    for (const options of requests) {
      void confirm(options).then((ok) => answers.push(ok));
    }
  };
  const result = renderV1(
    <>
      <Button onClick={onAsk}>Ask</Button>
      <ConfirmHost />
    </>,
    OUTSIDE,
  );
  const opener = screen.getByRole("button", { name: "Ask" });
  return { ...result, answers, opener };
}

async function shown(title: string) {
  const dialog = await screen.findByRole("alertdialog", { name: title });
  passGuard();
  return dialog;
}

async function ask(user: UserEvent, opener: HTMLElement, title: string) {
  await user.click(opener);
  return shown(title);
}

const scrim = () =>
  document.querySelector<HTMLElement>(
    "[data-slot=dialog-scrim]",
  ) as HTMLElement;
const button = (name: string) => screen.getByRole("button", { name });

describe("ConfirmHost", () => {
  it("resolves true on the action button and returns focus to the opener", async () => {
    const { user, opener, answers } = setup(STANDARD);
    await ask(user, opener, STANDARD.title);
    expect(button("Regenerate key")).toHaveFocus();
    await user.click(button("Regenerate key"));
    await waitFor(() => expect(answers).toEqual([true]));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it.each([
    ["Cancel", (user: UserEvent) => user.click(button("Cancel"))],
    ["Escape", (user: UserEvent) => user.keyboard("{Escape}")],
    ["an outside click", (user: UserEvent) => user.click(scrim())],
  ])("resolves false on %s", async (_path, close) => {
    const { user, opener, answers } = setup(STANDARD);
    await ask(user, opener, STANDARD.title);
    await close(user);
    await waitFor(() => expect(answers).toEqual([false]));
  });

  it("ignores an answer that comes straight after the request shows", async () => {
    const { user, opener, answers } = setup(STANDARD);
    await user.click(opener);
    await screen.findByRole("alertdialog", { name: STANDARD.title });
    await user.click(button("Cancel"));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    passGuard();
    await user.click(button("Cancel"));
    await waitFor(() => expect(answers).toEqual([false]));
  });

  it("states the consequence, starts on Cancel and ignores an outside click when destructive", async () => {
    const { user, opener } = setup(DESTRUCTIVE);
    const dialog = await ask(user, opener, DESTRUCTIVE.title);
    expect(dialog).toHaveAccessibleDescription(
      "The endpoint stops responding immediately. This cannot be undone.",
    );
    expect(button("Cancel")).toHaveFocus();
    await user.click(scrim());
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("offers only Close and the link when blocked, and the link resolves false", async () => {
    const onSelect = vi.fn();
    const { user, opener, answers } = setup(blocked(onSelect));
    await ask(user, opener, "Invoice Vendor Lookup cannot be deleted");
    const footer = button("Open project").parentElement;
    expect(footer?.querySelectorAll("button")).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Close" })[1]).toHaveFocus();
    await user.click(button("Open project"));
    await waitFor(() => expect(answers).toEqual([false]));
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it("ignores the link straight after a blocked request shows", async () => {
    const onSelect = vi.fn();
    const { user, opener } = setup(blocked(onSelect));
    await user.click(opener);
    await screen.findByRole("alertdialog");
    await user.click(button("Open project"));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("stays busy while the action runs, then resolves true", async () => {
    let finish: () => void = () => undefined;
    const action = () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      });
    const { user, opener, answers } = setup({ ...DESTRUCTIVE, action });
    await ask(user, opener, DESTRUCTIVE.title);
    await user.click(button("Delete deployment"));
    expect(button("Delete deployment")).toHaveAttribute("aria-busy", "true");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    finish();
    await waitFor(() => expect(answers).toEqual([true]));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("stays open, logs and shows the error in the dialog when the action fails", async () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const action = () => Promise.reject(new Error("409"));
    const { user, opener, answers } = setup({ ...DESTRUCTIVE, action }, SECOND);
    const dialog = await ask(user, opener, DESTRUCTIVE.title);
    await user.click(button("Delete deployment"));
    await waitFor(() => expect(error).toHaveBeenCalledOnce());
    expect(button("Delete deployment")).not.toHaveAttribute("aria-busy");
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "Something went wrong. Try again.",
    );
    await user.click(button("Cancel"));
    await waitFor(() => expect(answers).toEqual([false]));
    await shown(SECOND.title);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("words the error with describeError and clears it when the action runs again", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let calls = 0;
    const action = () => {
      calls += 1;
      return calls === 1
        ? Promise.reject(new Error("409"))
        : new Promise<void>(() => undefined);
    };
    const describeError = (error: unknown) => ({
      title: `Not deleted: ${(error as Error).message}`,
      requestId: "req-9",
    });
    const { user } = renderV1(
      <>
        <Button onClick={() => void confirm({ ...DESTRUCTIVE, action })}>
          Ask
        </Button>
        <ConfirmHost describeError={describeError} />
      </>,
      OUTSIDE,
    );
    const dialog = await ask(user, button("Ask"), DESTRUCTIVE.title);
    await user.click(button("Delete deployment"));
    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("Not deleted: 409Request ID req-9");
    // First in the body, so a long details list cannot push it out of view.
    expect(alert.parentElement?.firstElementChild).toBe(alert);
    await user.click(button("Delete deployment"));
    expect(button("Delete deployment")).toHaveAttribute("aria-busy", "true");
    expect(within(dialog).queryByRole("alert")).toBeNull();
  });

  it("refuses a confirm() asked from inside an action, so the dialog cannot lock", async () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const inner: boolean[] = [];
    const action = async () => {
      inner.push(await confirm(blocked(vi.fn())));
    };
    const { user, opener, answers } = setup({ ...DESTRUCTIVE, action });
    await ask(user, opener, DESTRUCTIVE.title);
    await user.click(button("Delete deployment"));
    await waitFor(() => expect(answers).toEqual([true]));
    expect(inner).toEqual([false]);
    expect(error).toHaveBeenCalledWith(
      "[v1 confirm] called while an action runs: %s",
      "Invoice Vendor Lookup cannot be deleted",
    );
  });

  it("shows a queued request next, focuses its default button, then returns focus", async () => {
    const { user, opener, answers } = setup(STANDARD, DESTRUCTIVE);
    await ask(user, opener, STANDARD.title);
    await user.click(button("Regenerate key"));
    await shown(DESTRUCTIVE.title);
    await waitFor(() => expect(button("Cancel")).toHaveFocus());
    await user.click(button("Cancel"));
    await waitFor(() => expect(answers).toEqual([true, false]));
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("returns focus to the opener after a confirm asked right after another", async () => {
    const answers: boolean[] = [];
    const chain = async () => {
      if (await confirm(STANDARD)) {
        answers.push(await confirm(SECOND));
      }
    };
    const { user } = renderV1(
      <>
        <Button onClick={() => void chain()}>Chain</Button>
        <ConfirmHost />
      </>,
    );
    await ask(user, button("Chain"), STANDARD.title);
    await user.click(button("Regenerate key"));
    await shown(SECOND.title);
    await user.click(button("Cancel"));
    await waitFor(() => expect(answers).toEqual([false]));
    await waitFor(() => expect(button("Chain")).toHaveFocus());
  });

  it("lets a double click on the action answer only the request it started on", async () => {
    const { user, opener, answers } = setup(STANDARD, DESTRUCTIVE);
    await ask(user, opener, STANDARD.title);
    await user.dblClick(button("Regenerate key"));
    await waitFor(() => expect(answers).toEqual([true]));
    expect(
      screen.getByRole("alertdialog", { name: DESTRUCTIVE.title }),
    ).toBeInTheDocument();
  });

  it.each([
    ["Cancel", () => button("Cancel")],
    [
      "the header Close",
      () => screen.getAllByRole("button", { name: "Close" })[0],
    ],
    ["the dim layer", scrim],
  ])("lets a double click on %s answer only the request it started on", async (_target, target) => {
    const { user, opener, answers } = setup(STANDARD, SECOND);
    await ask(user, opener, STANDARD.title);
    await user.dblClick(target());
    await waitFor(() => expect(answers).toEqual([false]));
    expect(
      screen.getByRole("alertdialog", { name: SECOND.title }),
    ).toBeInTheDocument();
  });

  // user-event never sets `repeat`, so a dispatched repeat stands in for a held key.
  const held = (target: Element, key: string) => {
    const init = { key, repeat: true, bubbles: true, cancelable: true };
    const event = new KeyboardEvent("keydown", init);
    target.dispatchEvent(event);
    return event.defaultPrevented;
  };

  it("cancels a held Enter, so it cannot answer the next request, but a single Enter answers", async () => {
    const { user, opener, answers } = setup(STANDARD);
    await ask(user, opener, STANDARD.title);
    expect(held(button("Regenerate key"), "Enter")).toBe(true);
    expect(held(button("Regenerate key"), "a")).toBe(false);
    expect(button("Regenerate key")).toHaveFocus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(answers).toEqual([true]));
  });

  it("ignores a held Escape, so it cannot dismiss the next request", async () => {
    const { user, opener, answers } = setup(STANDARD, SECOND);
    await ask(user, opener, STANDARD.title);
    await user.keyboard("{Escape}");
    await shown(SECOND.title);
    held(document.activeElement ?? document.body, "Escape");
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(answers).toEqual([false]);
    expect(
      screen.getByRole("alertdialog", { name: SECOND.title }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(answers).toEqual([false, false]));
  });
});
