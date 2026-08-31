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

/*
 * Server-side paging, which every resource list uses: the page fetches
 * `?page=N&page_size=10` and hands this table ONE page of rows plus the real
 * row count as `total`. Sizing the pager off `dataSource.length` instead makes
 * every such list look like it has exactly one page — the LLM settings screen
 * held 12 adapters and offered no way to reach the last two.
 */
describe("DataTable server-side pagination", () => {
  const serverPage = (props) => (
    <DataTable
      columns={columns}
      dataSource={rowsFor(10)}
      rowKey="id"
      pagination={{ current: 1, pageSize: 10, total: 12 }}
      {...props}
    />
  );

  it("sizes the pager from `total`, not from the rows it was handed", () => {
    render(serverPage());
    expect(within(pager()).getByLabelText("Page 2")).toBeInTheDocument();
    expect(within(pager()).getByLabelText("Next page")).not.toBeDisabled();
  });

  /*
   * antd slices `dataSource` only when it holds more rows than fit on a page,
   * so a page of exactly `pageSize` rows must be rendered whole. Slicing it
   * again would show 10 rows on "page 1" and nothing on "page 2".
   */
  it("renders the whole page it was given without re-slicing it", () => {
    render(serverPage());
    expect(screen.getByText("Row 1")).toBeInTheDocument();
    expect(screen.getByText("Row 10")).toBeInTheDocument();
  });

  it("reports the requested page through antd's onChange", async () => {
    const onChange = vi.fn();
    render(serverPage({ onChange }));
    await userEvent.click(within(pager()).getByLabelText("Page 2"));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ current: 2, pageSize: 10, total: 12 }),
      expect.anything(),
      expect.anything(),
    );
  });

  it("reports the requested page from the next arrow too", async () => {
    const onChange = vi.fn();
    render(serverPage({ onChange }));
    await userEvent.click(within(pager()).getByLabelText("Next page"));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ current: 2 }),
      expect.anything(),
      expect.anything(),
    );
  });

  /*
   * `current` makes the pager controlled: the parent refetches and feeds the
   * new page back down. Moving locally would blank the body, because the rows
   * for page 2 are not in `dataSource` yet.
   */
  it("stays on the parent's page until new rows arrive", async () => {
    const onChange = vi.fn();
    render(serverPage({ onChange }));
    await userEvent.click(within(pager()).getByLabelText("Page 2"));
    expect(within(pager()).getByLabelText("Page 1")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByText("Row 1")).toBeInTheDocument();
  });

  it("follows the parent to the page it fetched", () => {
    const { rerender } = render(serverPage());
    rerender(
      serverPage({
        dataSource: [{ id: 11, name: "Row 11" }, { id: 12, name: "Row 12" }],
        pagination: { current: 2, pageSize: 10, total: 12 },
      }),
    );
    expect(within(pager()).getByLabelText("Page 2")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByText("Row 11")).toBeInTheDocument();
    expect(within(pager()).getByLabelText("Next page")).toBeDisabled();
  });

  /*
   * ResourceTable passes `showTotal` to render "Page 1 of 2 · 12 items" beside
   * the buttons; the pager read only `pageSize` off `pagination` and dropped it.
   */
  it("renders showTotal with the real count and range", () => {
    render(
      serverPage({
        pagination: {
          current: 1,
          pageSize: 10,
          total: 12,
          showTotal: (total, range) =>
            `${range[0]}-${range[1]} of ${total} items`,
        },
      }),
    );
    expect(within(pager()).getByText("1-10 of 12 items")).toBeInTheDocument();
  });

  /*
   * The last page holds fewer rows than `pageSize`; the range must stop at the
   * real count rather than at `current * pageSize`.
   */
  it("clamps the showTotal range on the last page", () => {
    render(
      serverPage({
        dataSource: [{ id: 11, name: "Row 11" }, { id: 12, name: "Row 12" }],
        pagination: {
          current: 2,
          pageSize: 10,
          total: 12,
          showTotal: (total, range) =>
            `${range[0]}-${range[1]} of ${total} items`,
        },
      }),
    );
    expect(within(pager()).getByText("11-12 of 12 items")).toBeInTheDocument();
  });

  /*
   * The whole loop, end to end, against a parent that behaves like ToolSettings:
   * it answers `onChange` by fetching that page and feeding the rows back down.
   *
   * This is the one that catches the ping-pong. TanStack calls
   * `resetPageIndex()` itself whenever `data` changes, so bridging its
   * `onPaginationChange` back to the parent meant page 2's rows arriving
   * immediately asked for page 1 — the pager snapped back within a frame and
   * the last two adapters stayed just as unreachable as before the fix. Every
   * assertion below still passed with that bridge in place; only driving a real
   * round trip shows it.
   */
  it("settles on the fetched page instead of bouncing back to the first", async () => {
    const pageOf = (n) =>
      n === 1 ? rowsFor(10) : [{ id: 11, name: "Row 11" }];
    const fetched = [];

    function Harness() {
      const [page, setPage] = useState(1);
      return (
        <DataTable
          columns={columns}
          dataSource={pageOf(page)}
          rowKey="id"
          pagination={{ current: page, pageSize: 10, total: 11 }}
          onChange={(p) => {
            fetched.push(p.current);
            setPage(p.current);
          }}
        />
      );
    }

    render(<Harness />);
    await userEvent.click(within(pager()).getByLabelText("Page 2"));

    await waitFor(() =>
      expect(screen.getByText("Row 11")).toBeInTheDocument(),
    );
    expect(fetched).toEqual([2]);
    expect(within(pager()).getByLabelText("Page 2")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByText("Row 1")).not.toBeInTheDocument();
  });

  /*
   * A search that narrows 12 rows to 3 leaves `current` at 2 for one render.
   * Unclamped, the pager pointed past the end and the body went blank.
   */
  it("clamps a stale page past the end of a shrunken list", () => {
    render(
      serverPage({
        dataSource: rowsFor(3),
        pagination: { current: 2, pageSize: 10, total: 3 },
      }),
    );
    expect(within(pager()).getByLabelText("Page 1")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByText("Row 1")).toBeInTheDocument();
  });
});

/*
 * Two antd Table props this wrapper claims to support and silently did not.
 * Both failed the same way: undeclared, they fell into `...props` and were
 * spread onto the wrapper <div>, where React drops an unknown attribute without
 * a word. Nothing threw, nothing logged, and the existing tests — which assert
 * what RENDERS — passed against a table that had quietly stopped responding to
 * clicks. Prompt Studio and Workflows became unopenable that way.
 */
describe("DataTable antd row/layout props", () => {
  it("calls onRow and wires the returned handlers to the row", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(2)}
        rowKey="id"
        onRow={(record) => ({ onClick: () => onClick(record) })}
      />,
    );

    await user.click(screen.getByText("Row 2"));

    expect(onClick).toHaveBeenCalledTimes(1);
    // The record, not TanStack's row wrapper — call-sites read `record.id`.
    expect(onClick.mock.calls[0][0]).toMatchObject({ id: 2, name: "Row 2" });
  });

  it("passes the record's index to onRow as antd does", () => {
    const onRow = vi.fn(() => ({}));
    render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(2)}
        rowKey="id"
        onRow={onRow}
      />,
    );
    expect(onRow.mock.calls.map((c) => c[1])).toEqual([0, 1]);
  });

  it("applies tableLayout to the table element", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(1)}
        rowKey="id"
        tableLayout="fixed"
      />,
    );
    // Without this the column `width`s are only hints, and one long cell
    // stretches its column until the trailing ones leave the viewport.
    expect(container.querySelector("table")).toHaveStyle({
      tableLayout: "fixed",
    });
  });

  it("leaves the table layout alone when the prop is absent", () => {
    const { container } = render(
      <DataTable columns={columns} dataSource={rowsFor(1)} rowKey="id" />,
    );
    expect(container.querySelector("table").style.tableLayout).toBe("");
  });
});

describe("DataTable showHeader", () => {
  it("renders the column headers by default", () => {
    const { container } = render(
      <DataTable columns={columns} dataSource={rowsFor(1)} rowKey="id" />,
    );
    expect(container.querySelector("thead")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
  });

  /*
   * antd omits the <thead> entirely for `showHeader={false}` rather than
   * emitting an empty one, and ~12 CSS rules in the app target
   * `.ant-table-thead` (heights, sticky offsets) that an empty header row
   * would still reserve space for.
   */
  it("omits the header entirely when showHeader is false", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(1)}
        rowKey="id"
        showHeader={false}
      />,
    );
    expect(container.querySelector("thead")).not.toBeInTheDocument();
    expect(screen.queryByText("Name")).not.toBeInTheDocument();
    // The body still renders — this hides the header, not the table.
    expect(screen.getByText("Row 1")).toBeInTheDocument();
  });
});

/*
 * antd's banded header: a column carrying `title` + `children` instead of a
 * `dataIndex`. Ignoring `children` collapsed the band to one accessor-less
 * leaf, which is how the LLMWhisperer processing-modes table came to render
 * its title over sixteen empty rows.
 */
describe("DataTable grouped columns", () => {
  const grouped = [
    {
      title: "Processing Modes",
      children: [
        { title: "Name", dataIndex: "feature", key: "feature" },
        { title: "Native Text", dataIndex: "nativeText", key: "nativeText" },
      ],
    },
  ];
  const rows = [{ key: "1", feature: "Cost", nativeText: "$1/1,000 pages" }];

  it("renders the band title and its leaf titles as two header rows", () => {
    const { container } = render(
      <DataTable
        columns={grouped}
        dataSource={rows}
        rowKey="key"
        pagination={false}
      />,
    );
    expect(container.querySelectorAll("thead tr")).toHaveLength(2);
    expect(screen.getByText("Processing Modes")).toBeInTheDocument();
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Native Text")).toBeInTheDocument();
  });

  it("renders a cell per leaf column, not one blank cell per row", () => {
    render(
      <DataTable
        columns={grouped}
        dataSource={rows}
        rowKey="key"
        pagination={false}
      />,
    );
    expect(screen.getByText("Cost")).toBeInTheDocument();
    expect(screen.getByText("$1/1,000 pages")).toBeInTheDocument();
    expect(document.querySelectorAll("tbody tr td")).toHaveLength(2);
  });

  it("spans the band across its leaves so the header rows line up", () => {
    const { container } = render(
      <DataTable
        columns={grouped}
        dataSource={rows}
        rowKey="key"
        pagination={false}
      />,
    );
    const [bandRow, leafRow] = container.querySelectorAll("thead tr");
    expect(bandRow.querySelectorAll("th")).toHaveLength(1);
    expect(bandRow.querySelector("th")).toHaveAttribute("colspan", "2");
    expect(leafRow.querySelectorAll("th")).toHaveLength(2);
  });

  it("honours a leaf column's render as antd does", () => {
    render(
      <DataTable
        columns={[
          {
            title: "Band",
            children: [
              {
                title: "Name",
                dataIndex: "feature",
                key: "feature",
                render: (value) => <b>{`rendered ${value}`}</b>,
              },
            ],
          },
        ]}
        dataSource={rows}
        rowKey="key"
        pagination={false}
      />,
    );
    expect(screen.getByText("rendered Cost")).toBeInTheDocument();
  });

  /*
   * Child indices restart at 0 inside every band, so an index-derived id
   * collides with a top-level column's — and TanStack rejects duplicate ids.
   */
  it("keeps ids unique when neither band nor leaf declares a key", () => {
    expect(() =>
      render(
        <DataTable
          columns={[
            { title: "Band", children: [{ title: "A", dataIndex: "feature" }] },
          ]}
          dataSource={rows}
          rowKey="key"
          pagination={false}
        />,
      ),
    ).not.toThrow();
    expect(screen.getByText("Cost")).toBeInTheDocument();
  });

  it("spans the empty state across every leaf column", () => {
    const { container } = render(
      <DataTable
        columns={grouped}
        dataSource={[]}
        rowKey="key"
        pagination={false}
      />,
    );
    expect(container.querySelector("tbody td")).toHaveAttribute("colspan", "2");
  });
});

/*
 * antd's `scroll={{ x, y }}`. Ten call-sites pass it; before it was declared it
 * fell into `...props` and onto the wrapper <div>, so every one of them got a
 * table at full height with no pinned header.
 */
describe("DataTable scroll", () => {
  // shadcn's own overflow wrapper is the scrolling ancestor, so the cap has to
  // land there for `position: sticky` to have anything to stick to.
  const scroller = (container) =>
    container.querySelector("table").parentElement;

  it("caps the scrolling wrapper at scroll.y", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(20)}
        rowKey="id"
        pagination={false}
        scroll={{ y: 500 }}
      />,
    );
    const wrapper = container.querySelector(".ant-table-container");
    // The cap is declared here but applies to the child — assert the child is
    // the element that actually scrolls.
    expect(wrapper).toHaveClass("[&>div]:max-h-[var(--table-scroll-y)]");
    expect(wrapper).toHaveStyle({ "--table-scroll-y": "500px" });
    expect(scroller(container).parentElement).toBe(wrapper);
    expect(scroller(container)).toHaveClass("overflow-auto");
  });

  it("passes a string scroll.y through as the caller wrote it", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(3)}
        rowKey="id"
        scroll={{ y: "calc(100vh - 450px)" }}
      />,
    );
    expect(container.querySelector(".ant-table-container")).toHaveStyle({
      "--table-scroll-y": "calc(100vh - 450px)",
    });
  });

  it("pins the header rows when the body scrolls", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(20)}
        rowKey="id"
        scroll={{ y: 500 }}
      />,
    );
    const th = container.querySelector("thead th");
    expect(th).toHaveStyle({ position: "sticky", top: "0px" });
    // The <tr> carries the background and border, and a pinned cell leaves the
    // row behind — so the cell has to bring its own.
    expect(th).toHaveClass("bg-[var(--neutral-50)]");
  });

  it("leaves the header unpinned without scroll.y", () => {
    const { container } = render(
      <DataTable columns={columns} dataSource={rowsFor(3)} rowKey="id" />,
    );
    expect(container.querySelector("thead th").style.position).toBe("");
    expect(container.querySelector(".ant-table-container")).not.toHaveClass(
      "[&>div]:max-h-[var(--table-scroll-y)]",
    );
  });

  it("gives the table a minimum width for scroll.x", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(3)}
        rowKey="id"
        scroll={{ x: 1200 }}
      />,
    );
    expect(container.querySelector("table")).toHaveStyle({
      minWidth: "1200px",
    });
  });

  it("reads scroll.x === true as max-content, as antd does", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(3)}
        rowKey="id"
        scroll={{ x: true }}
      />,
    );
    expect(container.querySelector("table")).toHaveStyle({
      minWidth: "max-content",
    });
  });

  it("keeps tableLayout working alongside scroll.x", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(3)}
        rowKey="id"
        tableLayout="fixed"
        scroll={{ x: "max-content" }}
      />,
    );
    expect(container.querySelector("table")).toHaveStyle({
      tableLayout: "fixed",
      minWidth: "max-content",
    });
  });

  it("does not leak scroll onto the DOM as an attribute", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(3)}
        rowKey="id"
        scroll={{ x: 900, y: 400 }}
      />,
    );
    expect(
      container.querySelector(".ant-table-wrapper").getAttribute("scroll"),
    ).toBeNull();
  });
});

/*
 * `bordered` was the fourth antd prop to reach the wrapper <div> instead of
 * being consumed, after onRow, showHeader and scroll. This one was noisier
 * than the others — React rejects it outright ("Received `true` for a
 * non-boolean attribute `bordered`") on every render — but just as invisible
 * to the suite, because a console error fails nothing.
 */
describe("DataTable bordered", () => {
  it("draws cell rules when asked", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(2)}
        rowKey="id"
        bordered
      />,
    );
    expect(container.querySelector("table").className).toContain(
      "ant-table-bordered",
    );
  });

  it("leaves the table unbordered by default", () => {
    const { container } = render(
      <DataTable columns={columns} dataSource={rowsFor(2)} rowKey="id" />,
    );
    expect(container.querySelector("table").className).not.toContain(
      "ant-table-bordered",
    );
  });

  it("does not leak bordered onto the DOM as an attribute", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        dataSource={rowsFor(2)}
        rowKey="id"
        bordered
      />,
    );
    expect(
      container.querySelector(".ant-table-wrapper").getAttribute("bordered"),
    ).toBeNull();
  });
});
