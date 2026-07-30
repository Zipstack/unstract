import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  Collapse,
  Dropdown,
  Modal,
  Tooltip,
} from "@/components/ui/shims/antd-overlays";

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

  // Dropdown.Button is a SPLIT button. ReviewHeader renders
  // <Dropdown.Button>Download File</Dropdown.Button>, and clicking the label
  // must download rather than open the menu — that separation is the entire
  // reason antd ships a distinct component from <Dropdown>.
  describe("Dropdown.Button (split button)", () => {
    it("fires onClick from the main half without opening the menu", () => {
      const onClick = vi.fn();
      const onMenuClick = vi.fn();
      render(
        <Dropdown.Button
          onClick={onClick}
          menu={{
            items: [{ key: "csv", label: "As CSV" }],
            onClick: onMenuClick,
          }}
        >
          Download File
        </Dropdown.Button>,
      );

      fireEvent.click(screen.getByRole("button", { name: "Download File" }));
      expect(onClick).toHaveBeenCalledTimes(1);
      expect(screen.queryByText("As CSV")).not.toBeInTheDocument();
      expect(onMenuClick).not.toHaveBeenCalled();
    });

    it("opens the menu from the chevron half", async () => {
      render(
        <Dropdown.Button menu={{ items: [{ key: "csv", label: "As CSV" }] }}>
          Download File
        </Dropdown.Button>,
      );

      const chevron = screen.getByRole("button", { name: "More actions" });
      expect(chevron).toHaveAttribute("aria-haspopup", "menu");
      // Radix opens menus on pointerdown, not click.
      fireEvent.pointerDown(
        chevron,
        new PointerEvent("pointerdown", { bubbles: true, button: 0 }),
      );
      expect(await screen.findByText("As CSV")).toBeInTheDocument();
    });

    it("disables both halves together", () => {
      render(
        <Dropdown.Button disabled menu={{ items: [] }}>
          Download File
        </Dropdown.Button>,
      );
      expect(
        screen.getByRole("button", { name: "Download File" }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "More actions" }),
      ).toBeDisabled();
    });
  });

  /*
   * `activeKey` is antd's CONTROLLED open state, and it is the ONLY way any
   * call-site in this app opens a Collapse — the prompt card, the notes card
   * and the LLM-profile form all render their own chevron in a header row
   * above the panel and feed the result back in as `activeKey`. The shim
   * originally read only `defaultActiveKey`, so `activeKey` fell through to
   * `...props`, landed on the DOM as an unknown attribute, and every panel
   * stayed shut: each prompt card showed its title bar and nothing else — no
   * prompt text, no coverage, no LLM profile, no output.
   *
   * These assert VISIBILITY rather than mere rendering. A smoke test that only
   * checked the tree rendered would have passed against the broken shim.
   */
  describe("Collapse activeKey (antd parity)", () => {
    it("shows the panel body when activeKey names the panel", () => {
      render(
        <Collapse activeKey={"1"}>
          <Collapse.Panel key="1" showArrow={false}>
            card body
          </Collapse.Panel>
        </Collapse>,
      );
      expect(screen.getByText("card body")).toBeVisible();
    });

    // Call-sites write `activeKey={expandCard && "1"}`, so a closed card hands
    // the shim `false` — which must read as "closed", not as a key.
    it("hides the body when activeKey is false", () => {
      render(
        <Collapse activeKey={false}>
          <Collapse.Panel key="1" showArrow={false}>
            card body
          </Collapse.Panel>
        </Collapse>,
      );
      expect(screen.queryByText("card body")).not.toBeInTheDocument();
    });

    it("follows activeKey when the parent toggles it", () => {
      const { rerender } = render(
        <Collapse activeKey={false}>
          <Collapse.Panel key="1" showArrow={false}>
            card body
          </Collapse.Panel>
        </Collapse>,
      );
      expect(screen.queryByText("card body")).not.toBeInTheDocument();

      rerender(
        <Collapse activeKey={"1"}>
          <Collapse.Panel key="1" showArrow={false}>
            card body
          </Collapse.Panel>
        </Collapse>,
      );
      expect(screen.getByText("card body")).toBeVisible();
    });

    it("opens an `items` panel from activeKey too", () => {
      render(
        <Collapse
          activeKey={"1"}
          items={[{ key: "1", label: "Advanced", children: "settings body" }]}
        />,
      );
      expect(screen.getByText("settings body")).toBeVisible();
    });

    // AddLlmProfile drives its panel from onChange; without it the header is dead.
    it("reports toggles through onChange", () => {
      const onChange = vi.fn();
      render(
        <Collapse
          activeKey={false}
          onChange={onChange}
          items={[{ key: "1", label: "Advanced", children: "settings body" }]}
        />,
      );
      fireEvent.click(screen.getByText("Advanced"));
      expect(onChange).toHaveBeenCalledWith(["1"]);
    });

    it("renders the caller's expandIcon with the active state", () => {
      render(
        <Collapse
          activeKey={"1"}
          expandIcon={({ isActive }) => <span>{isActive ? "open" : "shut"}</span>}
          items={[{ key: "1", label: "Advanced", children: "settings body" }]}
        />,
      );
      expect(screen.getByText("open")).toBeInTheDocument();
    });

    // A panel with no header and no arrow must not grow a stray empty bar.
    it("renders no header bar for a headerless, arrowless panel", () => {
      const { container } = render(
        <Collapse activeKey={"1"}>
          <Collapse.Panel key="1" showArrow={false}>
            card body
          </Collapse.Panel>
        </Collapse>,
      );
      expect(container.querySelector(".ant-collapse-header")).toBeNull();
    });

    // ghost/size are antd styling props; they must not reach the DOM.
    it("keeps antd-only styling props off the DOM", () => {
      const { container } = render(
        <Collapse ghost size="small" activeKey={"1"}>
          <Collapse.Panel key="1" showArrow={false}>
            card body
          </Collapse.Panel>
        </Collapse>,
      );
      const root = container.firstElementChild;
      expect(root.getAttribute("ghost")).toBeNull();
      expect(root.getAttribute("activeKey")).toBeNull();
    });

    it("still honours uncontrolled defaultActiveKey", () => {
      render(
        <Collapse defaultActiveKey={["1"]}>
          <Collapse.Panel key="1" showArrow={false}>
            card body
          </Collapse.Panel>
        </Collapse>,
      );
      expect(screen.getByText("card body")).toBeVisible();
    });
  });
});
