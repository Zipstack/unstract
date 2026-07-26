import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Modal, Tooltip } from "@/components/ui/antd-overlays";

describe("antd-compatible overlay shims (P2)", () => {
  it("renders nothing when closed", () => {
    render(<Modal open={false}>body</Modal>);
    expect(screen.queryByText("body")).not.toBeInTheDocument();
  });

  it("renders the body and title when open", () => {
    render(
      <Modal open title="My title">
        body
      </Modal>,
    );
    expect(screen.getByText("body")).toBeInTheDocument();
    expect(screen.getByText("My title")).toBeInTheDocument();
  });

  it("accepts the legacy `visible` alias antd used before `open`", () => {
    render(<Modal visible>legacy</Modal>);
    expect(screen.getByText("legacy")).toBeInTheDocument();
  });

  // The default-footer behaviour is the easiest thing to lose in a naive swap:
  // antd renders OK/Cancel unless footer={null}.

  it("renders a default OK/Cancel footer like antd does", () => {
    render(<Modal open>body</Modal>);
    expect(screen.getByRole("button", { name: "OK" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("suppresses the footer entirely for footer={null}", () => {
    render(
      <Modal open footer={null}>
        body
      </Modal>,
    );
    expect(
      screen.queryByRole("button", { name: "OK" }),
    ).not.toBeInTheDocument();
  });

  it("renders a custom footer when one is supplied", () => {
    render(
      <Modal open footer={<button type="button">Custom</button>}>
        body
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "Custom" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "OK" }),
    ).not.toBeInTheDocument();
  });

  it("honours custom okText/cancelText", () => {
    render(
      <Modal open okText="Save" cancelText="Discard">
        body
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Discard" })).toBeInTheDocument();
  });

  it("fires onOk and onCancel from the default footer", () => {
    const onOk = vi.fn();
    const onCancel = vi.fn();
    render(
      <Modal open onOk={onOk} onCancel={onCancel}>
        body
      </Modal>,
    );
    screen.getByRole("button", { name: "OK" }).click();
    screen.getByRole("button", { name: "Cancel" }).click();
    expect(onOk).toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalled();
  });

  it("disables the OK button while confirmLoading", () => {
    render(
      <Modal open confirmLoading>
        body
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "OK" })).toBeDisabled();
  });

  it("unmounts the body for destroyOnClose when closed", () => {
    const { rerender } = render(
      <Modal open destroyOnClose>
        body
      </Modal>,
    );
    expect(screen.getByText("body")).toBeInTheDocument();
    rerender(
      <Modal open={false} destroyOnClose>
        body
      </Modal>,
    );
    expect(screen.queryByText("body")).not.toBeInTheDocument();
  });

  it("passes the trigger through untouched when a Tooltip has no title", () => {
    render(
      <Tooltip title="">
        <button type="button">plain</button>
      </Tooltip>,
    );
    expect(screen.getByRole("button", { name: "plain" })).toBeInTheDocument();
  });

  it("still renders its child when a Tooltip does have a title", () => {
    render(
      <Tooltip title="hint">
        <button type="button">hoverable</button>
      </Tooltip>,
    );
    expect(
      screen.getByRole("button", { name: "hoverable" }),
    ).toBeInTheDocument();
  });
});
