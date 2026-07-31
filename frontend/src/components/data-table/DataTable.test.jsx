import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { DataTable } from "./DataTable";

/**
 * The pager is the part of this table users compare most directly against the
 * reference: antd renders a compact strip of square numbered buttons, not a
 * "Previous / Page 1 of 1 / Next" text row.
 */

const columns = [{ key: "name", dataIndex: "name", title: "Name" }];

const rowsFor = (n) =>
  Array.from({ length: n }, (_, i) => ({ id: i + 1, name: `Row ${i + 1}` }));

function pager() {
  return document.querySelector(".ant-pagination");
}

describe("DataTable rowSelection", () => {
  /*
   * antd tolerates an inline `rowSelection={{ selectedRowKeys, onChange }}`,
   * which is what most call-sites write — a fresh object on every render.
   * Depending on that object (or on the TanStack `table`, likewise rebuilt each
   * render) re-ran the mirror effect on every commit, and because the effect
   * calls back into the parent's setState that is an infinite loop. It crashed
   * the File History modal outright with React #185.
   */
  it("does not loop when rowSelection is an inline object", () => {
    function Harness() {
      const [keys, setKeys] = useState([]);
      return (
        <DataTable
          columns={columns}
          dataSource={rowsFor(2)}
          rowKey="id"
          rowSelection={{ selectedRowKeys: keys, onChange: setKeys }}
        />
      );
    }
    expect(() => render(<Harness />)).not.toThrow();
    expect(screen.getByText("Row 1")).toBeInTheDocument();
  });

  it("still reports the selected keys through onChange", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(2)}
        rowKey="id"
        rowSelection={{ onChange }}
      />,
    );
    await userEvent.click(screen.getAllByLabelText("Select row")[0]);
    // The first call fires on mount with an empty selection, as antd's does.
    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith(
        [1],
        expect.arrayContaining([expect.objectContaining({ id: 1 })]),
      ),
    );
  });
});

describe("DataTable pagination", () => {
  it("renders numbered page buttons rather than a Previous/Next text row", () => {
    render(
      <DataTable columns={columns} dataSource={rowsFor(25)} rowKey="id" />,
    );
    expect(screen.queryByText(/Page 1 of/)).not.toBeInTheDocument();
    expect(within(pager()).getByLabelText("Page 2")).toBeInTheDocument();
    expect(within(pager()).getByLabelText("Page 3")).toBeInTheDocument();
  });

  it("marks the current page for assistive tech", () => {
    render(
      <DataTable columns={columns} dataSource={rowsFor(25)} rowKey="id" />,
    );
    expect(within(pager()).getByLabelText("Page 1")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("moves to the page whose number was clicked", async () => {
    render(
      <DataTable columns={columns} dataSource={rowsFor(25)} rowKey="id" />,
    );
    await userEvent.click(within(pager()).getByLabelText("Page 3"));
    expect(screen.getByText("Row 21")).toBeInTheDocument();
    expect(screen.queryByText("Row 1")).not.toBeInTheDocument();
  });

  it("disables the arrows at the ends of the range", async () => {
    render(
      <DataTable columns={columns} dataSource={rowsFor(25)} rowKey="id" />,
    );
    const p = pager();
    expect(within(p).getByLabelText("Previous page")).toBeDisabled();
    await userEvent.click(within(p).getByLabelText("Page 3"));
    expect(within(p).getByLabelText("Next page")).toBeDisabled();
  });

  /*
   * antd keeps the pager a fixed width past 7 pages by collapsing the middle,
   * so a 200-row table must not render 20 buttons in a row.
   */
  it("collapses the middle with an ellipsis on long ranges", () => {
    render(
      <DataTable columns={columns} dataSource={rowsFor(200)} rowKey="id" />,
    );
    const p = pager();
    expect(within(p).getByText("…")).toBeInTheDocument();
    expect(within(p).getByLabelText("Page 20")).toBeInTheDocument();
    expect(within(p).queryByLabelText("Page 10")).not.toBeInTheDocument();
  });

  /*
   * antd's `hideOnSinglePage` defaults to FALSE — Manage Documents shows a
   * footer under its one-row table in the reference.
   */
  it("keeps the pager on a single page unless hideOnSinglePage is set", () => {
    const { rerender } = render(
      <DataTable columns={columns} dataSource={rowsFor(3)} rowKey="id" />,
    );
    expect(pager()).toBeInTheDocument();

    rerender(
      <DataTable
        columns={columns}
        dataSource={rowsFor(3)}
        rowKey="id"
        pagination={{ hideOnSinglePage: true }}
      />,
    );
    expect(pager()).not.toBeInTheDocument();
  });

  it("renders no pager at all when pagination is false", () => {
    render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(25)}
        rowKey="id"
        pagination={false}
      />,
    );
    expect(pager()).not.toBeInTheDocument();
    expect(screen.getByText("Row 25")).toBeInTheDocument();
  });
});
