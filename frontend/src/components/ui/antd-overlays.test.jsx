import { fireEvent, render, screen } from "@testing-library/react";
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

  // Regression: `centered` used to add a duplicate centring utility, which
  // tailwind-merge resolved by dropping the base translate — leaving the
  // dialog at transform:none, pinned to the top with its header clipped.
  it("keeps the base centring transform when centered is passed", () => {
    render(
      <Modal open centered title="Centred">
        body
      </Modal>,
    );
    const dlg = document.querySelector("[role='dialog']");
    expect(dlg).toBeTruthy();
    const cls = dlg.className;
    // The base transform must survive.
    expect(cls).toContain("translate-y-[-50%]");
    expect(cls).toContain("translate-x-[-50%]");
    // And the conflicting spelling must not be present.
    expect(cls).not.toContain("-translate-y-1/2");
  });

  it("does not leak `centered` onto the DOM", () => {
    render(
      <Modal open centered>
        body
      </Modal>,
    );
    const dlg = document.querySelector("[role='dialog']");
    expect(dlg.getAttribute("centered")).toBeNull();
  });

  // Regression: the adapter settings form rendered 1109px tall in an 800px
  // viewport, pushing the dialog to y=-194 with Submit unreachable. antd caps
  // .ant-modal-body; without that element the app's existing CSS matched
  // nothing.
  it("wraps content in a scrollable .ant-modal-body", () => {
    render(
      <Modal open title="Tall">
        <div>form fields</div>
      </Modal>,
    );
    const body = document.querySelector(".ant-modal-body");
    expect(body).toBeTruthy();
    expect(body.className).toContain("overflow-y-auto");
    expect(body.className).toContain("max-h-[70vh]");
    expect(body.textContent).toContain("form fields");
  });

  // Regression: ConfirmModal (12 consumers — delete buttons across prompt
  // studio, workflows, top nav) calls Modal.useModal() on every click. It was
  // undefined, so each of those screens threw a TypeError when clicked.
  it("Modal.useModal returns [api, contextHolder] like antd", () => {
    function Harness() {
      const [api, holder] = Modal.useModal();
      return (
        <>
          <button
            type="button"
            onClick={() =>
              api.confirm({ title: "Delete this?", onOk: () => undefined })
            }
          >
            open
          </button>
          {holder}
        </>
      );
    }
    render(<Harness />);
    expect(screen.getByRole("button", { name: "open" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    expect(screen.getByText("Delete this?")).toBeInTheDocument();
  });

  it("Modal.useModal fires onOk when confirmed", () => {
    const onOk = vi.fn();
    function Harness() {
      const [api, holder] = Modal.useModal();
      return (
        <>
          <button
            type="button"
            onClick={() => api.confirm({ title: "Sure?", okText: "Yes", onOk })}
          >
            open
          </button>
          {holder}
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "open" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(onOk).toHaveBeenCalled();
  });
});
