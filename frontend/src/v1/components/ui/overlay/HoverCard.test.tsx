import { act, screen } from "@testing-library/react";
import { Button, Link } from "@v1/components/ui/button";
import { renderV1 } from "@v1/test";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "./HoverCard";

function ModelHoverCard() {
  return (
    <>
      <Button>Before</Button>
      <HoverCard>
        <HoverCardTrigger asChild>
          <Link href="#gpt-4o">gpt-4o</Link>
        </HoverCardTrigger>
        <HoverCardContent>
          <p>OpenAI · 128k context</p>
        </HoverCardContent>
      </HoverCard>
    </>
  );
}

function setup() {
  return renderV1(<ModelHoverCard />, {
    userEventOptions: { advanceTimers: vi.advanceTimersByTime },
  });
}

async function waitOpenDelay() {
  await act(async () => {
    vi.advanceTimersByTime(500);
  });
}

describe("HoverCard", () => {
  beforeEach(() => {
    // Real time keeps user-event moving; the delays themselves are advanced by hand.
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("opens only after the delay on keyboard focus and keeps focus on the trigger", () => {
    // A clock without wall time, so a slow runner cannot open it early.
    vi.useRealTimers();
    vi.useFakeTimers();
    setup();
    const link = screen.getByRole("link", { name: "gpt-4o" });
    act(() => link.focus());
    act(() => vi.advanceTimersByTime(499));
    expect(screen.queryByText("OpenAI · 128k context")).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByText("OpenAI · 128k context")).toBeInTheDocument();
    expect(link).toHaveFocus();
  });

  it("closes only after the close delay once focus leaves", () => {
    vi.useRealTimers();
    vi.useFakeTimers();
    setup();
    const link = screen.getByRole("link", { name: "gpt-4o" });
    act(() => link.focus());
    act(() => vi.advanceTimersByTime(500));
    act(() => link.blur());
    act(() => vi.advanceTimersByTime(299));
    expect(screen.getByText("OpenAI · 128k context")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByText("OpenAI · 128k context")).toBeNull();
  });

  it("opens on hover after the delay", async () => {
    const { user } = setup();
    await user.hover(screen.getByRole("link", { name: "gpt-4o" }));
    await waitOpenDelay();
    expect(screen.getByText("OpenAI · 128k context")).toBeInTheDocument();
  });

  it("takes no asChild or forceMount on its content", () => {
    // @ts-expect-error the content renders its own surface
    const slotted = <HoverCardContent asChild />;
    // @ts-expect-error the content renders through its own portal
    const forced = <HoverCardContent forceMount />;
    expect([slotted, forced]).toHaveLength(2);
  });

  it("closes on Escape", async () => {
    const { user } = setup();
    await user.tab();
    await user.tab();
    await waitOpenDelay();
    await user.keyboard("{Escape}");
    expect(screen.queryByText("OpenAI · 128k context")).toBeNull();
    expect(screen.getByRole("link", { name: "gpt-4o" })).toHaveFocus();
  });

  it("closes when focus moves away", async () => {
    const { user } = setup();
    await user.tab();
    await user.tab();
    await waitOpenDelay();
    await user.tab({ shift: true });
    await waitOpenDelay();
    expect(screen.queryByText("OpenAI · 128k context")).toBeNull();
  });
});
