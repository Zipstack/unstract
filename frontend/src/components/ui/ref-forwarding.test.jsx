import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Dropdown } from "@/components/ui/antd-overlays";
import { Button } from "@/components/ui/button";
import { CustomButton } from "@/components/widgets/custom-button/CustomButton";

/**
 * Regression: Prompt Studio's Export button did nothing — no menu, no network
 * request. It is a `<Dropdown>` child, and Radix's trigger renders with
 * `asChild`, attaching its handlers through a ref. Neither CustomButton nor
 * the base shadcn Button forwarded refs, so the trigger was silently inert.
 *
 * A ref that goes nowhere throws no error and logs nothing, which is why this
 * survived every other test.
 */
describe("ref forwarding through the trigger chain", () => {
  it("the base Button forwards its ref to a DOM node", () => {
    let node = null;
    render(
      <Button
        ref={(n) => {
          node = n;
        }}
      >
        base
      </Button>,
    );
    expect(node).toBeInstanceOf(HTMLElement);
    expect(node.tagName).toBe("BUTTON");
  });

  it("CustomButton forwards its ref through to the DOM node", () => {
    let node = null;
    render(
      <CustomButton
        ref={(n) => {
          node = n;
        }}
      >
        custom
      </CustomButton>,
    );
    expect(node).toBeInstanceOf(HTMLElement);
    expect(node.tagName).toBe("BUTTON");
  });

  it("a Dropdown wrapping CustomButton wires up its trigger", () => {
    render(
      <Dropdown menu={{ items: [{ key: "a", label: "Export as Tool" }] }}>
        <CustomButton type="primary">Export</CustomButton>
      </Dropdown>,
    );
    const trigger = screen.getByRole("button", { name: "Export" });
    // Radix marks a wired-up trigger with aria-haspopup + its own state attr.
    expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
    expect(trigger.getAttribute("data-state")).toBe("closed");
  });

  it("that Dropdown actually opens on click", async () => {
    render(
      <Dropdown menu={{ items: [{ key: "a", label: "Export as Tool" }] }}>
        <CustomButton type="primary">Export</CustomButton>
      </Dropdown>,
    );
    fireEvent.pointerDown(screen.getByRole("button", { name: "Export" }), {
      button: 0,
      ctrlKey: false,
      pointerType: "mouse",
    });
    await waitFor(() =>
      expect(screen.getByText("Export as Tool")).toBeInTheDocument(),
    );
  });
});
