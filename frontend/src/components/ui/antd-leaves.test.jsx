import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  Alert,
  Avatar,
  Divider,
  Empty,
  Progress,
  Spin,
  Tag,
} from "@/components/ui/antd-leaves";

describe("antd-compatible leaf shims (P1-06)", () => {
  it("renders Tag content", () => {
    render(<Tag>beta</Tag>);
    expect(screen.getByText("beta")).toBeInTheDocument();
  });

  it("maps antd colour tokens onto Badge variants", () => {
    const { container } = render(<Tag color="success">ok</Tag>);
    expect(container.firstChild.className).toContain("bg-success");
  });

  it("maps error/red onto the destructive variant", () => {
    const { container } = render(<Tag color="red">bad</Tag>);
    expect(container.firstChild.className).toContain("destructive");
  });

  // One call-site passes a raw rgb() that antd applied directly — it must not
  // be silently dropped just because it is not a known token.
  it("falls through to inline style for a raw CSS colour", () => {
    const { container } = render(<Tag color="rgb(45, 183, 245)">custom</Tag>);
    expect(container.firstChild.style.backgroundColor).toBe(
      "rgb(45, 183, 245)",
    );
  });

  it("renders a close affordance only when closable", () => {
    const onClose = vi.fn();
    render(
      <Tag closable onClose={onClose}>
        x
      </Tag>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders Spin as a status indicator", () => {
    render(<Spin />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders Spin's tip text when supplied", () => {
    render(<Spin tip="Loading data" />);
    expect(screen.getByText("Loading data")).toBeInTheDocument();
  });

  it("renders Alert message and description", () => {
    render(<Alert message="Heads up" description="More detail" />);
    expect(screen.getByText("Heads up")).toBeInTheDocument();
    expect(screen.getByText("More detail")).toBeInTheDocument();
  });

  it("uses the destructive variant for type=error", () => {
    const { container } = render(<Alert type="error" message="Bad" />);
    expect(container.firstChild.className).toContain("destructive");
  });

  it("Alert dismisses itself when closable, and calls onClose", () => {
    const onClose = vi.fn();
    render(<Alert closable onClose={onClose} message="Dismiss me" />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
    expect(screen.queryByText("Dismiss me")).not.toBeInTheDocument();
  });

  it("renders a horizontal Divider by default", () => {
    const { container } = render(<Divider />);
    expect(container.firstChild).toBeTruthy();
  });

  it("renders Divider label text when given children", () => {
    render(<Divider>OR</Divider>);
    expect(screen.getByText("OR")).toBeInTheDocument();
  });

  it("Empty shows a default description, and a custom one when given", () => {
    const { rerender } = render(<Empty />);
    expect(screen.getByText("No data")).toBeInTheDocument();
    rerender(<Empty description="Nothing here yet" />);
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
  });

  it("Avatar renders a fallback when there is no src", () => {
    render(<Avatar>AB</Avatar>);
    expect(screen.getByText("AB")).toBeInTheDocument();
  });

  it("Avatar accepts a numeric size as explicit dimensions", () => {
    const { container } = render(<Avatar size={48}>Z</Avatar>);
    expect(container.firstChild.style.width).toBe("48px");
  });

  it("Progress shows the rounded percentage", () => {
    render(<Progress percent={42.6} />);
    expect(screen.getByText("43%")).toBeInTheDocument();
  });

  it("Progress hides the readout when showInfo is false", () => {
    render(<Progress percent={50} showInfo={false} />);
    expect(screen.queryByText("50%")).not.toBeInTheDocument();
  });
});
