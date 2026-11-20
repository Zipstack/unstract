import { act, screen } from "@testing-library/react";
import { Button, IconButton } from "@v1/components/ui/button";
import { ACTION_ICONS } from "@v1/lib/icons";
import { renderV1 } from "@v1/test";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TOOLTIP_DELAY_MS, Tooltip } from "./Tooltip";

function setup() {
  return renderV1(
    <>
      <Button>Before</Button>
      <Tooltip content="Copy endpoint">
        <IconButton aria-label="Copy" icon={ACTION_ICONS.copy} />
      </Tooltip>
    </>,
    { userEventOptions: { advanceTimers: vi.advanceTimersByTime } },
  );
}

const copyButton = () => screen.getByRole("button", { name: "Copy" });

describe("Tooltip", () => {
  beforeEach(() => {
    // Real time keeps user-event moving; the delays themselves are advanced by hand.
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows at once on keyboard focus and describes its trigger", async () => {
    const { user } = setup();
    await user.tab();
    await user.tab();
    expect(copyButton()).toHaveFocus();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Copy endpoint");
    expect(copyButton()).toHaveAccessibleDescription("Copy endpoint");
  });

  it("shows on hover only after the delay", async () => {
    const { user } = setup();
    await user.hover(copyButton());
    expect(screen.queryByRole("tooltip")).toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(TOOLTIP_DELAY_MS);
    });
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("hides on Escape and leaves focus on the trigger", async () => {
    const { user } = setup();
    await user.tab();
    await user.tab();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(copyButton()).toHaveFocus();
  });

  it("hides when the pointer moves away", async () => {
    const { user } = setup();
    await user.hover(copyButton());
    await act(async () => {
      vi.advanceTimersByTime(TOOLTIP_DELAY_MS);
    });
    await user.unhover(copyButton());
    // Then on, past Radix's grace area between the trigger and the tooltip.
    await user.pointer({
      target: screen.getByRole("button", { name: "Before" }),
      coords: { clientX: 400, clientY: 400 },
    });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("takes text only", () => {
    const icon = <IconButton aria-label="Copy" icon={ACTION_ICONS.copy} />;
    // @ts-expect-error a tooltip never holds interactive content
    const interactive = <Tooltip content={<a href="#x">x</a>}>{icon}</Tooltip>;
    expect(interactive).toBeTruthy();
  });
});
