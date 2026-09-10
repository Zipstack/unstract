import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "@/components/ui/shims/antd-button";
import {
  Checkbox,
  Input,
  InputNumber,
  Radio,
  Select,
  Switch,
} from "@/components/ui/shims/antd-inputs";
import {
  Collapse,
  Dropdown,
  Modal,
  Popconfirm,
  Popover,
  Tooltip,
} from "@/components/ui/shims/antd-overlays";
import {
  Card,
  Menu,
  Table,
  Tabs,
  Upload,
} from "@/components/ui/shims/antd-structure";

/**
 * `data-testid` has to survive the shim layer, or every id written at a
 * call-site is dead weight.
 *
 * Five shims swallowed it. `Select`, `Popover` and `Popconfirm` spread
 * `...props` onto a Radix *Root*, which renders no DOM at all; `Dropdown` and
 * `Tabs` destructured `...props` and then never used it. In all five cases the
 * attribute vanished with no warning — the same silent prop-drop this layer
 * keeps producing, and indistinguishable at a call-site from a typo in the id.
 *
 * It is worth guarding rather than eyeballing because the failure only shows up
 * in Playwright, against a running stack, as a locator that matches nothing.
 *
 * Where the id lands is a deliberate choice per component, not an accident:
 *
 *   trigger   `Select` — the trigger is what a test clicks, and it is the only
 *             element the shim itself renders (all three modes: plain,
 *             `showSearch`, and `tags`, which render three different widgets).
 *
 *   content   `Modal`, `Dropdown`, `Popover`, `Popconfirm` — these are portalled
 *             out of the tree, so they have no stable position and only library
 *             classes to select on. Their triggers are `children`, which the
 *             call-site renders and can label itself. This also matches where
 *             each shim already sends its `ref`.
 */
describe("data-testid forwarding through the shims", () => {
  /*
   * These render their id straight onto a DOM node they own. Held as a table
   * because the point is coverage of the shim surface, not per-case nuance.
   */
  const passthrough = {
    Button: <Button data-testid="probe">x</Button>,
    Input: <Input data-testid="probe" />,
    InputNumber: <InputNumber data-testid="probe" />,
    Switch: <Switch data-testid="probe" />,
    Checkbox: <Checkbox data-testid="probe" />,
    Radio: <Radio data-testid="probe" />,
    Select: (
      <Select data-testid="probe" options={[{ value: "a", label: "A" }]} />
    ),
    // `showSearch` is a hand-rolled combobox, not Radix's Select — a separate
    // component with a separate trigger, so a separate case.
    SelectSearch: (
      <Select
        showSearch
        data-testid="probe"
        options={[{ value: "a", label: "A" }]}
      />
    ),
    // `tags` mode is a third widget again (TagsInput), reached by an early exit
    // before either of the paths above.
    SelectTags: <Select mode="tags" data-testid="probe" />,
    Modal: (
      <Modal open data-testid="probe">
        body
      </Modal>
    ),
    Tooltip: (
      <Tooltip data-testid="probe" title="t">
        <button type="button">t</button>
      </Tooltip>
    ),
    Popover: (
      <Popover open data-testid="probe" content="c">
        <button type="button">t</button>
      </Popover>
    ),
    Tabs: (
      <Tabs
        data-testid="probe"
        items={[{ key: "a", label: "A", children: "c" }]}
      />
    ),
    Collapse: (
      <Collapse
        data-testid="probe"
        items={[{ key: "a", label: "A", children: "c" }]}
      />
    ),
    Table: (
      <Table
        data-testid="probe"
        columns={[{ title: "C", dataIndex: "c" }]}
        dataSource={[{ key: 1, c: "v" }]}
      />
    ),
    Menu: <Menu data-testid="probe" items={[{ key: "a", label: "A" }]} />,
    Upload: (
      <Upload data-testid="probe">
        <button type="button">u</button>
      </Upload>
    ),
    Card: <Card data-testid="probe">c</Card>,
  };

  for (const [name, element] of Object.entries(passthrough)) {
    it(`${name} puts its data-testid on a DOM node`, () => {
      // `baseElement`, not `container`: the portalled ones render outside it.
      const { baseElement } = render(element);
      expect(
        baseElement.querySelector("[data-testid='probe']"),
        `${name} dropped its data-testid before the DOM`,
      ).not.toBeNull();
    });
  }

  /*
   * Menu entries and tab triggers are the repeated, library-classed elements
   * the naming plan calls out by name, and neither can be labelled from the
   * call-site: both are built by the shim from a data descriptor. They derive
   * an id from the PARENT's, so a call-site opts in once instead of per entry,
   * and the result stays readable — `ws-actions-item-run`, not `tab-1`.
   */
  it("Dropdown labels its portalled menu and each of its items", async () => {
    const { baseElement } = render(
      <Dropdown
        data-testid="probe"
        menu={{ items: [{ key: "a", label: "A" }] }}
      >
        <button type="button">t</button>
      </Dropdown>,
    );

    // Radix opens on pointerdown, not click.
    fireEvent.pointerDown(screen.getByRole("button", { name: "t" }), {
      button: 0,
      ctrlKey: false,
      pointerType: "mouse",
    });

    await waitFor(() =>
      expect(
        baseElement.querySelector("[data-testid='probe']"),
        "the menu panel is unreachable",
      ).not.toBeNull(),
    );
    expect(
      baseElement.querySelector("[data-testid='probe-item-a']"),
      "menu items are unreachable",
    ).not.toBeNull();
  });

  it("Popconfirm labels its panel and both of its buttons", async () => {
    const { baseElement } = render(
      <Popconfirm
        data-testid="probe"
        title="Delete?"
        okText="Yes"
        cancelText="No"
      >
        <button type="button">t</button>
      </Popconfirm>,
    );

    fireEvent.click(screen.getByRole("button", { name: "t" }));

    await waitFor(() =>
      expect(
        baseElement.querySelector("[data-testid='probe']"),
        "the confirm panel is unreachable",
      ).not.toBeNull(),
    );
    expect(
      baseElement.querySelector("[data-testid='probe-ok']"),
      "the confirm button is unreachable",
    ).not.toBeNull();
    expect(
      baseElement.querySelector("[data-testid='probe-cancel']"),
      "the cancel button is unreachable",
    ).not.toBeNull();
  });

  it("Tabs labels each of its triggers", () => {
    const { baseElement } = render(
      <Tabs
        data-testid="probe"
        items={[
          { key: "a", label: "A", children: "c" },
          { key: "b", label: "B", children: "d" },
        ]}
      />,
    );
    expect(
      baseElement.querySelector("[data-testid='probe-tab-a']"),
    ).not.toBeNull();
    expect(
      baseElement.querySelector("[data-testid='probe-tab-b']"),
    ).not.toBeNull();
  });

  it("an explicit id on an item beats the derived one", () => {
    const { baseElement } = render(
      <Tabs
        data-testid="probe"
        items={[
          {
            key: "8f14e45f-ceea-467a-9a3f-1b2c3d4e5f60",
            label: "A",
            children: "c",
            "data-testid": "doc-parser-tab-schema",
          },
        ]}
      />,
    );
    expect(
      baseElement.querySelector("[data-testid='doc-parser-tab-schema']"),
    ).not.toBeNull();
  });

  /*
   * Deriving must stay opt-in. Without this, every tab and menu entry in the
   * app would silently grow an id like `tab-1` — not unique across two tab
   * strips on one page, and exactly the generic naming the plan forbids.
   */
  it("derives nothing when the parent has no data-testid", () => {
    const { baseElement } = render(
      <Tabs items={[{ key: "a", label: "A", children: "c" }]} />,
    );
    expect(baseElement.querySelector("[data-testid]")).toBeNull();
  });
});
