import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  Badge,
  Card,
  Descriptions,
  Drawer,
  Layout,
  List,
  Menu,
  Pagination,
  Result,
  Segmented,
  Statistic,
  Table,
  Tabs,
  Transfer,
  Upload,
} from "@/components/ui/shims/antd-structure";

describe("antd-compatible structural shims (P4)", () => {
  it("Card renders title and body", () => {
    render(<Card title="Settings">content</Card>);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("Card renders the `extra` slot", () => {
    render(<Card title="T" extra={<button type="button">More</button>} />);
    expect(screen.getByRole("button", { name: "More" })).toBeInTheDocument();
  });

  it("Tabs renders labels from the `items` data prop", () => {
    render(
      <Tabs
        items={[
          { key: "1", label: "First", children: "one" },
          { key: "2", label: "Second", children: "two" },
        ]}
      />,
    );
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
  });

  /*
   * antd's default tab style is `line` (transparent strip, underlined active
   * label). shadcn's primitive ships the pill/card look, so Prompt Studio
   * rendered a grey rounded pill where the reference draws an underline.
   */
  it("Tabs default to antd's line style, not shadcn's pill", () => {
    render(<Tabs items={[{ key: "1", label: "One", children: "x" }]} />);
    const list = screen.getByRole("tablist");
    expect(list.className).toContain("bg-transparent");
    expect(list.className).toContain("rounded-none");
  });

  /*
   * The doc-manager toolbar centres these tabs against a file name and
   * buttons. Vertical padding inflates the label's own box (`pb-2` gave 36px,
   * `py-3` 48px) so the TEXT rides above the centre the row aligns on, ~5.6px
   * clear of the file name. antd's label box is 22px — the line height alone.
   */
  it("Tabs give line-style labels no vertical padding to inflate the box", () => {
    render(<Tabs items={[{ key: "1", label: "One", children: "x" }]} />);
    const cls = screen.getByRole("tab").className;
    expect(cls).toContain("py-0");
    expect(cls).not.toContain("pb-2");
    expect(cls).not.toContain("py-3");
  });

  /*
   * React never exposes `key` in props, so reading `c.props.key` gave every
   * TabPane `undefined` and nothing matched `activeKey`. The Output Analyzer's
   * profile tabs rendered permanently inactive with their panel `hidden`, and
   * onChange handed back the ".$"-prefixed key — which the call-site forwarded
   * as a profile id, producing a 500.
   */
  it("Tabs read the pane key off the ELEMENT, not props", () => {
    render(
      <Tabs activeKey="p2">
        <Tabs.TabPane tab="One" key="p1">
          first
        </Tabs.TabPane>
        <Tabs.TabPane tab="Two" key="p2">
          second
        </Tabs.TabPane>
      </Tabs>,
    );
    const selected = screen.getByRole("tab", { selected: true });
    expect(selected).toHaveTextContent("Two");
    expect(screen.getByText("second")).toBeInTheDocument();
  });

  it("Tabs report an unprefixed key through onChange", () => {
    const onChange = vi.fn();
    render(
      <Tabs activeKey="p1" onChange={onChange}>
        <Tabs.TabPane tab="One" key="p1" />
        <Tabs.TabPane tab="Two" key="p2" />
      </Tabs>,
    );
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Two" }));
    // ".$p2" here is what reached the backend as a profile id.
    expect(onChange).toHaveBeenCalledWith("p2");
  });

  it("Tabs keep the pill look when type='card'", () => {
    render(
      <Tabs type="card" items={[{ key: "1", label: "One", children: "x" }]} />,
    );
    expect(screen.getByRole("tablist").className).not.toContain(
      "bg-transparent",
    );
  });

  it("Tabs fires onChange with the selected key", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        onChange={onChange}
        items={[
          { key: "a", label: "A", children: "x" },
          { key: "b", label: "B", children: "y" },
        ]}
      />,
    );
    // Radix activates tabs on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "B" }));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("List renders each item through renderItem", () => {
    render(
      <List
        dataSource={[{ id: 1 }, { id: 2 }]}
        renderItem={(item) => <span>row {item.id}</span>}
      />,
    );
    expect(screen.getByText("row 1")).toBeInTheDocument();
    expect(screen.getByText("row 2")).toBeInTheDocument();
  });

  /*
   * antd renders an <Empty> illustration here, not a bare string. Asserting
   * only the TEXT is what let the icon go missing: "No data" floating alone
   * in a table reads as a rendering failure rather than an empty state.
   */
  it("List shows an empty state with an icon for no data", () => {
    const { container } = render(
      <List dataSource={[]} renderItem={() => null} />,
    );
    expect(screen.getByText("No data")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  // Table delegates to the shared DataTable (D5/D9).
  it("Table renders antd-style columns and dataSource", () => {
    render(
      <Table
        columns={[
          { title: "Name", dataIndex: "name", key: "name" },
          { title: "Role", dataIndex: "role", key: "role" },
        ]}
        dataSource={[
          { id: 1, name: "Ada", role: "admin" },
          { id: 2, name: "Grace", role: "user" },
        ]}
      />,
    );
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Ada")).toBeInTheDocument();
    expect(screen.getByText("Grace")).toBeInTheDocument();
  });

  it("Table honours a column's custom render(value, record)", () => {
    render(
      <Table
        columns={[
          {
            title: "Name",
            dataIndex: "name",
            key: "name",
            render: (value, record) => `${value} (#${record.id})`,
          },
        ]}
        dataSource={[{ id: 7, name: "Ada" }]}
      />,
    );
    expect(screen.getByText("Ada (#7)")).toBeInTheDocument();
  });

  it("Table shows an empty state when dataSource is empty", () => {
    const { container } = render(
      <Table
        columns={[{ title: "Name", dataIndex: "name", key: "name" }]}
        dataSource={[]}
      />,
    );
    expect(screen.getByText("No data")).toBeInTheDocument();
    // antd puts an <Empty> illustration here, not a bare string.
    expect(container.querySelector("svg")).not.toBeNull();
  });

  /*
   * antd's `.ant-table-thead > tr > th` is `background: #fafafa` with a 1px
   * #f0f0f0 bottom border (read off the reference's own stylesheet). shadcn
   * leaves the header transparent, so against the white table surface the
   * header row was indistinguishable from the body.
   */
  it("gives the Table header row a distinct background", () => {
    const { container } = render(
      <Table
        columns={[{ title: "Name", dataIndex: "name", key: "name" }]}
        dataSource={[{ key: "1", name: "a" }]}
      />,
    );
    const headerRow = container.querySelector("thead tr");
    expect(headerRow.className).toContain("neutral-50");
    expect(headerRow.className).toContain("border-b");
  });

  it("Table accepts antd's object form of `loading`", () => {
    const { container } = render(
      <Table
        columns={[{ title: "N", dataIndex: "n", key: "n" }]}
        dataSource={[]}
        loading={{ spinning: true }}
      />,
    );
    expect(container.querySelector("[role='status']")).toBeTruthy();
  });

  it("Result renders title and subTitle", () => {
    render(<Result status="success" title="Done" subTitle="All good" />);
    expect(screen.getByText("Done")).toBeInTheDocument();
    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("Segmented renders options and reports the picked value", () => {
    const onChange = vi.fn();
    render(
      <Segmented options={["Day", "Week"]} value="Day" onChange={onChange} />,
    );
    fireEvent.click(screen.getByText("Week"));
    expect(onChange).toHaveBeenCalledWith("Week");
  });

  it("Pagination reports the next page and page size", () => {
    const onChange = vi.fn();
    render(
      <Pagination current={1} pageSize={10} total={30} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onChange).toHaveBeenCalledWith(2, 10);
  });

  it("Pagination disables Previous on the first page", () => {
    render(<Pagination current={1} pageSize={10} total={30} />);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  });

  it("Descriptions renders label/value pairs", () => {
    render(
      <Descriptions items={[{ key: "a", label: "Owner", children: "Ada" }]} />,
    );
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("Ada")).toBeInTheDocument();
  });

  it("Statistic applies precision and suffix", () => {
    render(
      <Statistic title="Uptime" value={99.456} precision={1} suffix="%" />,
    );
    expect(screen.getByText("99.5")).toBeInTheDocument();
    expect(screen.getByText("%")).toBeInTheDocument();
  });

  // antd's Badge is a count overlay — NOT shadcn's pill Badge (antd calls that Tag).
  it("Badge overlays a count on its child", () => {
    render(
      <Badge count={5}>
        <span>inbox</span>
      </Badge>,
    );
    expect(screen.getByText("inbox")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("Badge caps the count at overflowCount", () => {
    render(<Badge count={150} overflowCount={99} />);
    expect(screen.getByText("99+")).toBeInTheDocument();
  });

  /**
   * antd applies `style` to the COUNT, not to the wrapper. PromptChangeIndicator
   * passes `style={{ backgroundColor: color }}` to tint its counter; letting it
   * fall through onto the wrapper painted a solid grey block behind the icon
   * button on every prompt card in Prompt Studio (7 of them on one screen).
   */
  it("Badge applies `style` to the count, not the wrapper", () => {
    const { container } = render(
      <Badge count={3} style={{ backgroundColor: "#bfbfbf" }}>
        <button type="button">act</button>
      </Badge>,
    );
    const wrapper = container.firstChild;
    expect(wrapper.style.backgroundColor).toBe("");
    expect(screen.getByText("3").style.backgroundColor).toBe("#bfbfbf");
  });

  it("Badge offsets the count when antd's `offset` is given", () => {
    render(
      <Badge count={2} offset={[-2, 12]}>
        <button type="button">act</button>
      </Badge>,
    );
    expect(screen.getByText("2").style.transform).toBe("translate(-2px, 12px)");
  });

  it("Badge hides a zero count unless showZero", () => {
    const { rerender } = render(<Badge count={0} />);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    rerender(<Badge count={0} showZero />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("Drawer renders its content when open", () => {
    render(
      <Drawer open title="Panel">
        drawer body
      </Drawer>,
    );
    expect(screen.getByText("drawer body")).toBeInTheDocument();
  });

  it("Transfer splits items across source and target by targetKeys", () => {
    render(
      <Transfer
        dataSource={[
          { key: "1", title: "Left item" },
          { key: "2", title: "Right item" },
        ]}
        targetKeys={["2"]}
      />,
    );
    expect(screen.getByText("Left item")).toBeInTheDocument();
    expect(screen.getByText("Right item")).toBeInTheDocument();
  });

  /*
   * antd's Transfer is a CHECKBOX widget: tick rows, then press the arrow
   * between the panels. The earlier stub moved whichever row was clicked and
   * drew no checkboxes, counts, search or arrows, so it read as a plain list
   * beside the reference.
   */
  it("Transfer moves the CHECKED rows when the arrow is pressed", () => {
    const onChange = vi.fn();
    render(
      <Transfer
        dataSource={[
          { key: "1", title: "Movable" },
          { key: "2", title: "Other" },
        ]}
        targetKeys={[]}
        onChange={onChange}
      />,
    );
    // Clicking the row alone must NOT move it.
    fireEvent.click(screen.getByText("Movable"));
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Move selected to the right"));
    expect(onChange).toHaveBeenCalledWith(["1"], "right", ["1"]);
  });

  it("Transfer moves back to the left from the target panel", () => {
    const onChange = vi.fn();
    render(
      <Transfer
        dataSource={[{ key: "1", title: "Movable" }]}
        targetKeys={["1"]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText("Movable"));
    fireEvent.click(screen.getByLabelText("Move selected to the left"));
    expect(onChange).toHaveBeenCalledWith([], "left", ["1"]);
  });

  it("Transfer disables an arrow when nothing on that side is checked", () => {
    render(
      <Transfer dataSource={[{ key: "1", title: "A" }]} targetKeys={[]} />,
    );
    expect(
      screen.getByLabelText("Move selected to the right"),
    ).toBeDisabled();
    expect(screen.getByLabelText("Move selected to the left")).toBeDisabled();
  });

  it("Transfer shows an item count per panel, like antd", () => {
    render(
      <Transfer
        dataSource={[
          { key: "1", title: "A" },
          { key: "2", title: "B" },
          { key: "3", title: "C" },
        ]}
        targetKeys={["3"]}
        titles={["Source", "Target"]}
      />,
    );
    expect(screen.getByText("2 items")).toBeInTheDocument();
    expect(screen.getByText("1 items")).toBeInTheDocument();
  });

  /* `showSearch` was accepted and silently dropped. */
  it("Transfer renders a filter box per panel when showSearch is set", () => {
    render(
      <Transfer
        showSearch
        dataSource={[
          { key: "1", title: "Alpha" },
          { key: "2", title: "Beta" },
        ]}
        targetKeys={[]}
      />,
    );
    const boxes = screen.getAllByPlaceholderText("Search here");
    expect(boxes).toHaveLength(2);

    fireEvent.change(boxes[0], { target: { value: "alp" } });
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByText("Beta")).not.toBeInTheDocument();
  });

  it("Transfer renders no filter box without showSearch", () => {
    render(
      <Transfer dataSource={[{ key: "1", title: "A" }]} targetKeys={[]} />,
    );
    expect(screen.queryByPlaceholderText("Search here")).not.toBeInTheDocument();
  });

  it("Transfer select-all checks every row in its own panel", () => {
    const onChange = vi.fn();
    render(
      <Transfer
        dataSource={[
          { key: "1", title: "A" },
          { key: "2", title: "B" },
        ]}
        targetKeys={[]}
        titles={["Source", "Target"]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByLabelText("Select all in Source"));
    fireEvent.click(screen.getByLabelText("Move selected to the right"));
    expect(onChange).toHaveBeenCalledWith(["1", "2"], "right", ["1", "2"]);
  });

  // Regression: these two bugs shipped to a dev deployment and produced an
  // icons-only sidebar sitting in a 240px gutter, plus an empty dashboard.

  it("Layout grows with flex-auto so nested flex:1 children get height", () => {
    const { container } = render(<Layout>content</Layout>);
    // flex-auto, NOT the default flex:0 1 auto — otherwise the element
    // computes to height 0 and every flex:1 descendant collapses.
    expect(container.firstChild.className).toContain("flex-auto");
  });

  it("Layout.Content also grows rather than staying flex-1", () => {
    const { container } = render(<Layout.Content>body</Layout.Content>);
    expect(container.firstChild.className).toContain("flex-auto");
  });

  it("Layout switches to a row when it contains a Sider", () => {
    const { container } = render(
      <Layout>
        <Layout.Sider>nav</Layout.Sider>
        <Layout.Content>body</Layout.Content>
      </Layout>,
    );
    expect(container.firstChild.className).toContain("flex-row");
  });

  // The real app renders its Sider inside <SideNavBar>, so child inspection
  // cannot see it — detection has to work at runtime, however deep it is.
  it("Layout detects a Sider nested inside another component", () => {
    function NestedNav() {
      return <Layout.Sider width={240}>nav</Layout.Sider>;
    }
    const { container } = render(
      <Layout>
        <NestedNav />
        <Layout.Content>body</Layout.Content>
      </Layout>,
    );
    expect(container.firstChild.className).toContain("flex-row");
    expect(container.firstChild.className).not.toContain("flex-col");
  });

  it("Layout stacks in a column with no Sider", () => {
    const { container } = render(
      <Layout>
        <Layout.Content>body</Layout.Content>
      </Layout>,
    );
    expect(container.firstChild.className).toContain("flex-col");
  });

  it("Sider renders at collapsedWidth when collapsed", () => {
    const { container } = render(
      <Layout.Sider width={240} collapsedWidth={65} collapsed>
        nav
      </Layout.Sider>,
    );
    expect(container.firstChild.style.width).toBe("65px");
  });

  it("Sider renders at full width when not collapsed", () => {
    const { container } = render(
      <Layout.Sider width={240} collapsedWidth={65} collapsed={false}>
        nav
      </Layout.Sider>,
    );
    expect(container.firstChild.style.width).toBe("240px");
  });

  /**
   * antd wraps a Sider's children in `.ant-layout-sider-children`, and
   * SideNavBar.css depends on it: that wrapper is the flex column which clamps
   * `.sidebar-content-wrapper` so its `overflow-y: auto` has something to
   * scroll against. Rendering children bare skipped the clamp, the scroll
   * wrapper grew to its full content height (929px in a 668px rail), and the
   * bottom menu items became unreachable.
   */
  it("Sider wraps children in .ant-layout-sider-children like antd", () => {
    const { container } = render(
      <Layout.Sider width={240}>
        <span>nav content</span>
      </Layout.Sider>,
    );
    const wrapper = container.querySelector(".ant-layout-sider-children");
    expect(wrapper).toBeTruthy();
    expect(wrapper.textContent).toContain("nav content");
    // The child must be INSIDE the wrapper, not a sibling of it.
    expect(container.firstChild.children).toHaveLength(1);
  });

  it("Sider does not leak antd-only props onto the DOM", () => {
    const { container } = render(
      <Layout.Sider width={240} collapsedWidth={65} collapsible trigger={null}>
        nav
      </Layout.Sider>,
    );
    const el = container.firstChild;
    expect(el.getAttribute("collapsedwidth")).toBeNull();
    expect(el.getAttribute("collapsible")).toBeNull();
  });

  // Regression: the adapter pickers pass grid={{ column: 4 }}; ignoring it
  // rendered one card per row in a tall scroller instead of a 4-up grid.
  it("List renders a grid when antd's grid prop is supplied", () => {
    const { container } = render(
      <List
        grid={{ gutter: 16, column: 4 }}
        dataSource={[{ id: 1 }, { id: 2 }]}
        renderItem={(i) => <span>item {i.id}</span>}
      />,
    );
    const root = container.firstChild;
    expect(root.className).toContain("grid");
    expect(root.className).toContain("grid-cols-4");
    expect(root.className).not.toContain("divide-y");
    expect(root.style.gap).toBe("16px");
  });

  /**
   * `divide-y` sets the border WIDTH only; Tailwind's default border colour is
   * black. Without an explicit divide colour every list row gained a solid
   * black rule where antd drew a near-invisible hairline.
   *
   * The token is `separator` (#f0f0f0), not `border` (#e5e5e5): antd draws
   * this rule at rgba(5,5,5,.06), and --border is four shades darker, which
   * reads as a hard rule between rows rather than a hairline.
   */
  /*
   * The row wrapper must add NO vertical padding.
   *
   * antd puts the 16px on `.ant-list-item`, which is what `renderItem`
   * returns, so padding the wrapper as well stacks a second 16+16px. That
   * shipped twice: `py-2` gave 96px rows and the "fix" to `py-4` gave 114px,
   * both against the reference's 82px — and jsdom reports no geometry, so
   * only the class list can catch it.
   */
  it("List does not pad the row wrapper (renderItem owns its padding)", () => {
    const { container } = render(
      <List dataSource={[{ id: 1 }]} renderItem={(i) => <span>{i.id}</span>} />,
    );
    const wrapper = container.firstChild.firstChild;
    expect(
      wrapper.className,
      "the wrapper must not add py-*; antd pads .ant-list-item, which renderItem returns",
    ).not.toMatch(/\bpy-\d/);
  });

  it("List colours its row dividers with the separator token", () => {
    const { container } = render(
      <List
        dataSource={[{ id: 1 }, { id: 2 }]}
        renderItem={(i) => <span>{i.id}</span>}
      />,
    );
    expect(container.firstChild.className).toContain("divide-separator");
  });

  it("List still stacks when no grid prop is given", () => {
    const { container } = render(
      <List dataSource={[{ id: 1 }]} renderItem={(i) => <span>{i.id}</span>} />,
    );
    expect(container.firstChild.className).toContain("divide-y");
    expect(container.firstChild.className).not.toContain("grid-cols");
  });
  /**
   * `Upload.Dragger = Upload` aliased the dragger to the plain inline Upload,
   * so the Import Project modal rendered its icon and help text with no drop
   * zone around them, and dropping a file did nothing.
   */
  describe("Upload.Dragger (antd parity)", () => {
    it("renders a dashed drop zone, not the inline Upload span", () => {
      const { container } = render(
        <Upload.Dragger>
          <p>Click or drag file to this area</p>
        </Upload.Dragger>,
      );
      expect(container.querySelector(".ant-upload-drag")).toBeTruthy();
      const zone = container.querySelector("[class*='border-dashed']");
      expect(zone).toBeTruthy();
      expect(screen.getByText(/Click or drag file/)).toBeInTheDocument();
    });

    it("accepts a dropped file and routes it through beforeUpload", async () => {
      const beforeUpload = vi.fn().mockReturnValue(false);
      const { container } = render(
        <Upload.Dragger beforeUpload={beforeUpload}>
          <p>drop here</p>
        </Upload.Dragger>,
      );
      const file = new File(["{}"], "project.json", {
        type: "application/json",
      });
      fireEvent.drop(container.querySelector(".ant-upload-drag"), {
        dataTransfer: { files: [file] },
      });
      await vi.waitFor(() =>
        expect(beforeUpload).toHaveBeenCalledWith(file, [file]),
      );
    });

    it("does not accept drops while disabled", () => {
      const beforeUpload = vi.fn();
      const { container } = render(
        <Upload.Dragger disabled beforeUpload={beforeUpload}>
          <p>drop here</p>
        </Upload.Dragger>,
      );
      fireEvent.drop(container.querySelector(".ant-upload-drag"), {
        dataTransfer: {
          files: [new File(["{}"], "x.json", { type: "application/json" })],
        },
      });
      expect(beforeUpload).not.toHaveBeenCalled();
    });
  });

  /*
   * The Settings menu passes an icon per item. Dropped straight into the flex
   * row, a LONG label squeezes the SVG to width 0 while leaving its height at
   * 24 — "SummarizedExtraction" rendered as a blank gap where every shorter
   * sibling showed its icon. The icon needs its own shrink-0 box.
   */
  describe("Menu icons", () => {
    it("renders an icon for every item, including long labels", () => {
      const { container } = render(
        <Menu
          items={[
            { key: "1", label: "Grammar", icon: <svg data-testid="i1" /> },
            {
              key: "2",
              label: "SummarizedExtraction",
              icon: <svg data-testid="i2" />,
            },
          ]}
        />,
      );
      expect(container.querySelectorAll("svg")).toHaveLength(2);
    });

    it("gives the icon a shrink-proof wrapper so a long label cannot crush it", () => {
      const { container } = render(
        <Menu
          items={[
            {
              key: "2",
              label: "SummarizedExtraction",
              icon: <svg data-testid="i2" />,
            },
          ]}
        />,
      );
      const wrapper = container.querySelector("svg").parentElement;
      expect(wrapper.className).toContain("shrink-0");
    });

    /*
     * antd marks the selected item with a PRIMARY tint and primary text, not
     * a grey. `bg-accent` resolved to the same #f5f5f5 as the hover state, so
     * the active settings page looked identical to an idle one.
     */
    it("distinguishes the selected item from the hover state", () => {
      render(
        <Menu
          selectedKeys={["1"]}
          items={[
            { key: "1", label: "Active" },
            { key: "2", label: "Idle" },
          ]}
        />,
      );
      const active = screen.getByText("Active").closest("button");
      const idle = screen.getByText("Idle").closest("button");
      expect(active.className).toContain("text-primary");
      expect(active.className).not.toContain("bg-accent");
      expect(idle.className).not.toContain("text-primary");
    });

    it("renders items that carry no icon", () => {
      render(<Menu items={[{ key: "1", label: "Plain" }]} />);
      expect(screen.getByText("Plain")).toBeInTheDocument();
    });
  });
});
