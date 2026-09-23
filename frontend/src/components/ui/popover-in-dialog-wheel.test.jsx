import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Select } from "@/components/ui/shims/antd-inputs";
import { Modal } from "@/components/ui/shims/antd-overlays";

/**
 * Wheel-scrolling a popover that is open inside a Modal.
 *
 * Radix's Dialog locks scrolling with react-remove-scroll, which listens for
 * `wheel` on `document` and preventDefaults any event whose target is neither
 * inside the lock nor inside one of its shards (the dialog content). Popover
 * content is portalled to `document.body`, so it is outside both — leaving
 * popover lists scrollable by dragging the scrollbar (a pointer interaction,
 * never a wheel event) but dead to the mouse wheel.
 *
 * Radix's own Select and DropdownMenu are not affected: their content carries
 * its own RemoveScroll, which takes over the lock stack while open. Only
 * Popover-based surfaces need this, so the assertion is on PopoverContent.
 */
function wheelOver(element) {
  const event = new WheelEvent("wheel", {
    deltaY: 100,
    bubbles: true,
    cancelable: true,
  });
  element.dispatchEvent(event);
  return event;
}

describe("popover wheel scrolling inside a Modal", () => {
  it("does not let the dialog's scroll lock cancel the wheel", async () => {
    const user = userEvent.setup();

    render(
      <Modal open title="Adapters">
        <Popover>
          <PopoverTrigger>open</PopoverTrigger>
          <PopoverContent>
            <div data-testid="scroller">content</div>
          </PopoverContent>
        </Popover>
      </Modal>,
    );

    await user.click(screen.getByText("open"));
    const event = wheelOver(await screen.findByTestId("scroller"));

    await waitFor(() => expect(event.defaultPrevented).toBe(false));
  });

  it("keeps a searchable Select's option list wheel-scrollable", async () => {
    const user = userEvent.setup();

    render(
      <Modal open title="Adapters">
        <Select
          showSearch
          placeholder="Select an LLM adapter"
          options={Array.from({ length: 40 }, (_, i) => ({
            value: `a${i}`,
            label: `adapter-${i}`,
          }))}
        />
      </Modal>,
    );

    await user.click(screen.getByRole("combobox"));
    const event = wheelOver(await screen.findByRole("listbox"));

    await waitFor(() => expect(event.defaultPrevented).toBe(false));
  });

  it("still calls a caller-supplied onWheel", async () => {
    const user = userEvent.setup();
    let seen = 0;

    render(
      <Popover>
        <PopoverTrigger>open</PopoverTrigger>
        <PopoverContent onWheel={() => seen++}>
          <div data-testid="scroller">content</div>
        </PopoverContent>
      </Popover>,
    );

    await user.click(screen.getByText("open"));
    wheelOver(await screen.findByTestId("scroller"));

    await waitFor(() => expect(seen).toBe(1));
  });
});
