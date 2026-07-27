import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  Badge,
  Card,
  Descriptions,
  Drawer,
  List,
  Pagination,
  Result,
  Segmented,
  Statistic,
  Table,
  Tabs,
  Transfer,
} from "@/components/ui/antd-structure";

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

  it("List shows an empty state for no data", () => {
    render(<List dataSource={[]} renderItem={() => null} />);
    expect(screen.getByText("No data")).toBeInTheDocument();
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
    render(
      <Table
        columns={[{ title: "Name", dataIndex: "name", key: "name" }]}
        dataSource={[]}
      />,
    );
    expect(screen.getByText("No data")).toBeInTheDocument();
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

  it("Transfer moves an item and reports the new targetKeys", () => {
    const onChange = vi.fn();
    render(
      <Transfer
        dataSource={[{ key: "1", title: "Movable" }]}
        targetKeys={[]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByText("Movable"));
    expect(onChange).toHaveBeenCalledWith(["1"], "right", ["1"]);
  });
});
