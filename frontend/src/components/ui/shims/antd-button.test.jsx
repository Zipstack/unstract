import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/ui/shims/antd-button";

describe("antd-compatible Button shim (P1-04)", () => {
  it("renders children in a real <button>", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("defaults to DOM type=button so it never submits a form by accident", () => {
    render(<Button>x</Button>);
    expect(screen.getByRole("button").getAttribute("type")).toBe("button");
  });

  it("maps htmlType onto the DOM type attribute", () => {
    render(<Button htmlType="submit">go</Button>);
    expect(screen.getByRole("button").getAttribute("type")).toBe("submit");
  });

  // The behaviours that made a find-and-replace unsafe:

  it("disables the button while loading, as antd does", () => {
    render(<Button loading>saving</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("shows a spinner when loading and hides the supplied icon", () => {
    render(
      <Button loading icon={<span data-testid="icon" />}>
        saving
      </Button>,
    );
    expect(screen.queryByTestId("icon")).not.toBeInTheDocument();
    expect(screen.getByRole("button").querySelector("svg")).toBeTruthy();
  });

  it("renders the icon when not loading", () => {
    render(<Button icon={<span data-testid="icon" />}>with icon</Button>);
    expect(screen.getByTestId("icon")).toBeInTheDocument();
  });

  it("keeps an explicitly disabled button disabled", () => {
    render(<Button disabled>nope</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("applies destructive styling for danger", () => {
    render(<Button danger>del</Button>);
    expect(screen.getByRole("button").className).toContain("destructive");
  });

  it("treats danger + text as a ghost button with destructive text", () => {
    render(
      <Button danger type="text">
        del
      </Button>,
    );
    expect(screen.getByRole("button").className).toContain("text-destructive");
  });

  it("makes block buttons full width", () => {
    render(<Button block>wide</Button>);
    expect(screen.getByRole("button").className).toContain("w-full");
  });

  it("rounds circle/round shapes", () => {
    render(<Button shape="circle">o</Button>);
    expect(screen.getByRole("button").className).toContain("rounded-full");
  });

  it("forwards onClick and arbitrary props", () => {
    let clicked = false;
    render(
      <Button data-testid="probe" onClick={() => (clicked = true)}>
        c
      </Button>,
    );
    screen.getByTestId("probe").click();
    expect(clicked).toBe(true);
  });
});
