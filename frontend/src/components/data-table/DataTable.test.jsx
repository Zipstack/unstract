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
        dataSource: [
          { id: 11, name: "Row 11" },
          { id: 12, name: "Row 12" },
        ],
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
        dataSource: [
          { id: 11, name: "Row 11" },
          { id: 12, name: "Row 12" },
        ],
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

    await waitFor(() => expect(screen.getByText("Row 11")).toBeInTheDocument());
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

/**
 * antd's column filters. The shim used to drop `filters`, `filterDropdown`,
 * `filterIcon`, `onFilter` and `filteredValue` on the floor, which is what
 * stripped the Execution ID search, the file-name search and the Status filter
 * off the Execution Logs screens during the shadcn migration.
 */
describe("DataTable column filters", () => {
  const typed = [
    { id: 1, name: "Row 1", type: "LOG" },
    { id: 2, name: "Row 2", type: "NOTIFICATION" },
  ];

  const typeColumn = (extra = {}) => ({
    title: "Type",
    dataIndex: "type",
    key: "type",
    filters: [
      { text: "LOG", value: "LOG" },
      { text: "NOTIFICATION", value: "NOTIFICATION" },
    ],
    ...extra,
  });

  async function openFilter(label = "Filter by Type") {
    await userEvent.click(screen.getByLabelText(label));
  }

  // The option labels double as cell values, so every query inside the panel
  // has to be scoped to it or it matches the table body too.
  const panel = () =>
    within(document.querySelector(".ant-table-filter-dropdown"));

  it("renders a filter trigger for a column that declares filters", () => {
    render(
      <DataTable columns={[...columns, typeColumn()]} dataSource={typed} />,
    );
    expect(screen.getByLabelText("Filter by Type")).toBeInTheDocument();
  });

  it("renders no trigger on a column with no filter at all", () => {
    render(<DataTable columns={columns} dataSource={typed} />);
    expect(screen.queryByLabelText("Filter by Name")).not.toBeInTheDocument();
  });

  it("applies onFilter locally once the selection is confirmed", async () => {
    render(
      <DataTable
        columns={[
          ...columns,
          typeColumn({ onFilter: (value, record) => record.type === value }),
        ]}
        dataSource={typed}
      />,
    );
    expect(screen.getByText("Row 2")).toBeInTheDocument();
    await openFilter();
    await userEvent.click(panel().getByText("LOG"));
    await userEvent.click(panel().getByRole("button", { name: "OK" }));
    expect(screen.getByText("Row 1")).toBeInTheDocument();
    expect(screen.queryByText("Row 2")).not.toBeInTheDocument();
  });

  /*
   * antd holds the draft until OK: ticking a box must not filter the table
   * underneath the open panel.
   */
  it("leaves the rows alone until OK is pressed", async () => {
    render(
      <DataTable
        columns={[
          ...columns,
          typeColumn({ onFilter: (value, record) => record.type === value }),
        ]}
        dataSource={typed}
      />,
    );
    await openFilter();
    await userEvent.click(panel().getByText("LOG"));
    expect(screen.getByText("Row 2")).toBeInTheDocument();
  });

  it("puts every row back when the filter is reset", async () => {
    render(
      <DataTable
        columns={[
          ...columns,
          typeColumn({ onFilter: (value, record) => record.type === value }),
        ]}
        dataSource={typed}
      />,
    );
    await openFilter();
    await userEvent.click(panel().getByText("LOG"));
    await userEvent.click(panel().getByRole("button", { name: "OK" }));
    expect(screen.queryByText("Row 2")).not.toBeInTheDocument();
    await openFilter();
    await userEvent.click(panel().getByRole("button", { name: "Reset" }));
    expect(screen.getByText("Row 2")).toBeInTheDocument();
  });

  /*
   * `filters` with no `onFilter` is antd's server-side filter — the Execution
   * Logs status filter. Applying it locally would hide rows the server was
   * about to replace.
   */
  it("does not filter locally when the column has no onFilter", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[...columns, typeColumn()]}
        dataSource={typed}
        onChange={onChange}
      />,
    );
    await openFilter();
    await userEvent.click(panel().getByText("LOG"));
    await userEvent.click(panel().getByRole("button", { name: "OK" }));
    expect(screen.getByText("Row 2")).toBeInTheDocument();
    expect(onChange).toHaveBeenCalledWith(
      expect.anything(),
      { type: ["LOG"] },
      {},
    );
  });

  it("sends the reader back to the first page when a filter changes", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[...columns, typeColumn()]}
        dataSource={typed}
        pagination={{ current: 4, pageSize: 10, total: 40 }}
        onChange={onChange}
      />,
    );
    await openFilter();
    await userEvent.click(panel().getByText("LOG"));
    await userEvent.click(panel().getByRole("button", { name: "OK" }));
    expect(onChange.mock.calls[0][0]).toMatchObject({ current: 1 });
  });

  it("reports null rather than an empty list for an untouched filters column", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          ...columns,
          typeColumn(),
          typeColumn({ title: "Level", key: "level" }),
        ]}
        dataSource={typed}
        onChange={onChange}
      />,
    );
    await openFilter();
    await userEvent.click(panel().getByText("LOG"));
    await userEvent.click(panel().getByRole("button", { name: "OK" }));
    // Every filterable column gets an entry, active or not: LogModal indexes
    // straight into `filters.level[0]` and a missing key is a TypeError.
    expect(onChange.mock.calls[0][1]).toEqual({ type: ["LOG"], level: null });
  });

  it("selects only one option at a time when filterMultiple is false", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[...columns, typeColumn({ filterMultiple: false })]}
        dataSource={typed}
        onChange={onChange}
      />,
    );
    await openFilter();
    await userEvent.click(panel().getByText("LOG"));
    await userEvent.click(panel().getByText("NOTIFICATION"));
    await userEvent.click(panel().getByRole("button", { name: "OK" }));
    expect(onChange.mock.calls[0][1]).toEqual({ type: ["NOTIFICATION"] });
  });

  it("narrows the option list when filterSearch is on", async () => {
    render(
      <DataTable
        columns={[...columns, typeColumn({ filterSearch: true })]}
        dataSource={typed}
      />,
    );
    await openFilter();
    await userEvent.type(
      panel().getByPlaceholderText("Search in filters"),
      "NOTIF",
    );
    expect(panel().queryByText("LOG")).not.toBeInTheDocument();
    expect(panel().getByText("NOTIFICATION")).toBeInTheDocument();
  });

  it("seeds the selection from defaultFilteredValue", async () => {
    render(
      <DataTable
        columns={[
          ...columns,
          typeColumn({
            defaultFilteredValue: ["LOG"],
            onFilter: (value, record) => record.type === value,
          }),
        ]}
        dataSource={typed}
      />,
    );
    expect(screen.queryByText("Row 2")).not.toBeInTheDocument();
  });

  it("marks the trigger active while a filter is applied", async () => {
    render(
      <DataTable
        columns={[...columns, typeColumn({ filteredValue: ["LOG"] })]}
        dataSource={typed}
      />,
    );
    expect(screen.getByLabelText("Filter by Type")).toHaveAttribute(
      "data-filtered",
      "true",
    );
  });
});

describe("DataTable custom filterDropdown", () => {
  const rows = [{ id: 1, name: "Row 1" }];

  /*
   * LogsTable passes the execution-ID search box as a NODE, not a function: it
   * owns its own state and never calls back through the table at all.
   */
  it("renders a filterDropdown passed as a node", async () => {
    render(
      <DataTable
        columns={[
          {
            title: "Execution ID",
            dataIndex: "name",
            key: "executionId",
            filterDropdown: <input placeholder="Search execution ID" />,
          },
        ]}
        dataSource={rows}
      />,
    );
    await userEvent.click(screen.getByLabelText("Filter by Execution ID"));
    expect(
      screen.getByPlaceholderText("Search execution ID"),
    ).toBeInTheDocument();
  });

  /*
   * LogModal's level filter calls `setSelectedKeys([...])` and `confirm()` back
   * to back in one handler, so `confirm` has to publish the keys just set
   * rather than the ones React has yet to re-render with.
   */
  it("publishes keys set immediately before confirm in the same handler", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          {
            title: "Level",
            dataIndex: "name",
            key: "level",
            filterDropdown: ({ setSelectedKeys, confirm }) => (
              <button
                type="button"
                onClick={() => {
                  setSelectedKeys(["ERROR"]);
                  confirm();
                }}
              >
                Pick ERROR
              </button>
            ),
          },
        ]}
        dataSource={rows}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Filter by Level"));
    await userEvent.click(screen.getByRole("button", { name: "Pick ERROR" }));
    expect(onChange.mock.calls[0][1]).toEqual({ level: ["ERROR"] });
  });

  /*
   * antd reports a filterDropdown column's raw keys, so a cleared one is `[]`
   * and not `null` — LogModal reads `filters.level[0]`, which throws on null.
   */
  it("reports an empty list, not null, for a cleared filterDropdown column", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          {
            title: "Level",
            dataIndex: "name",
            key: "level",
            filterDropdown: ({ clearFilters }) => (
              <button type="button" onClick={clearFilters}>
                Clear
              </button>
            ),
          },
        ]}
        dataSource={rows}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Filter by Level"));
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onChange.mock.calls[0][1]).toEqual({ level: [] });
    expect(onChange.mock.calls[0][1].level[0]).toBeUndefined();
  });

  it("hands filterIcon the filtered flag as antd does", () => {
    render(
      <DataTable
        columns={[
          {
            title: "Level",
            dataIndex: "name",
            key: "level",
            filteredValue: ["ERROR"],
            filterDropdown: <div />,
            filterIcon: (filtered) => <span>{filtered ? "on" : "off"}</span>,
          },
        ]}
        dataSource={rows}
      />,
    );
    expect(screen.getByText("on")).toBeInTheDocument();
  });

  /*
   * The sort handler sits on the <th>, so a click on the icon nested inside it
   * would otherwise re-sort the column under the panel that just opened.
   */
  it("does not sort the column when the filter icon is clicked", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          {
            title: "Level",
            dataIndex: "name",
            key: "level",
            sorter: true,
            filterDropdown: <div />,
          },
        ]}
        dataSource={rows}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Filter by Level"));
    expect(onChange).not.toHaveBeenCalled();
  });
});

/**
 * antd reads the sorter's shape: a function sorts locally with that
 * comparator, `sorter: true` means the SERVER sorts and the table should only
 * report the click. Both used to sort locally with a guessed comparator.
 */
describe("DataTable sorting", () => {
  const rows = [
    { id: 1, name: "beta", size: 2 },
    { id: 2, name: "alpha", size: 10 },
  ];

  const bodyText = () =>
    Array.from(document.querySelectorAll("tbody tr")).map(
      (tr) => tr.querySelector("td").textContent,
    );

  it("sorts with the comparator the column supplied", async () => {
    render(
      <DataTable
        columns={[
          {
            title: "Name",
            dataIndex: "name",
            key: "name",
            sorter: (a, b) => a.name.localeCompare(b.name),
          },
        ]}
        dataSource={rows}
      />,
    );
    expect(bodyText()).toEqual(["beta", "alpha"]);
    await userEvent.click(screen.getByText("Name"));
    expect(bodyText()).toEqual(["alpha", "beta"]);
  });

  it("sorts ascending on the first click, as antd does", async () => {
    render(
      <DataTable
        columns={[
          {
            title: "Size",
            dataIndex: "size",
            key: "size",
            sorter: (a, b) => a.size - b.size,
          },
        ]}
        dataSource={rows}
      />,
    );
    await userEvent.click(screen.getByText("Size"));
    expect(bodyText()).toEqual(["2", "10"]);
  });

  /*
   * The rows on screen are one server page. Reordering them locally made the
   * Execution Logs list look sorted while the rows that belonged at the top
   * stayed on page two.
   */
  it("leaves a server-sorted column's rows in the order they arrived", async () => {
    render(
      <DataTable
        columns={[
          { title: "Name", dataIndex: "name", key: "name", sorter: true },
        ]}
        dataSource={rows}
      />,
    );
    await userEvent.click(screen.getByText("Name"));
    expect(bodyText()).toEqual(["beta", "alpha"]);
  });

  it("reports the sorted column through antd's onChange", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          {
            title: "Executed At",
            dataIndex: "executedAt",
            key: "executedAt",
            sorter: true,
          },
        ]}
        dataSource={rows}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByText("Executed At"));
    expect(onChange.mock.calls[0][2]).toMatchObject({
      field: "executedAt",
      columnKey: "executedAt",
      order: "ascend",
    });
    await userEvent.click(screen.getByText("Executed At"));
    expect(onChange.mock.calls[1][2]).toMatchObject({ order: "descend" });
  });

  it("reports an empty sorter once sorting is cleared", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          { title: "Name", dataIndex: "name", key: "name", sorter: true },
        ]}
        dataSource={rows}
        onChange={onChange}
      />,
    );
    const header = screen.getByText("Name");
    await userEvent.click(header);
    await userEvent.click(header);
    await userEvent.click(header);
    expect(onChange.mock.calls[2][2]).toEqual({});
  });
});

/**
 * The header's affordances: what a column ADVERTISES before it is touched, and
 * where the advertisement sits.
 *
 * Both were wrong on Execution Logs. A sortable column drew nothing at all
 * until it was sorted, so "Executed At" and "Execution Time" looked inert; and
 * the sorter and filter icons trailed the title inline, landing wherever each
 * title happened to end rather than on the right-hand rule antd puts them on.
 */
describe("DataTable header affordances", () => {
  const rows = [{ id: 1, name: "a" }];

  const sorterIn = (title) =>
    screen
      .getByText(title)
      .closest("th")
      .querySelector(".ant-table-column-sorter");

  it("shows a sortable column's sorter before it is sorted", () => {
    render(
      <DataTable
        columns={[
          { title: "Sortable", dataIndex: "name", key: "name", sorter: true },
          { title: "Plain", dataIndex: "name", key: "plain" },
        ]}
        dataSource={rows}
      />,
    );
    // Two carets, so the column reads as "sorts, currently unsorted" rather
    // than as an ordinary column.
    expect(sorterIn("Sortable").querySelectorAll("svg")).toHaveLength(2);
    // An unsortable column must not grow one.
    expect(sorterIn("Plain")).toBeNull();
  });

  it("marks the applied direction and only that one", async () => {
    render(
      <DataTable
        columns={[
          { title: "Sortable", dataIndex: "name", key: "name", sorter: true },
        ]}
        dataSource={rows}
      />,
    );
    const highlighted = () =>
      Array.from(sorterIn("Sortable").querySelectorAll("svg")).map((svg) =>
        svg.classList.contains("text-primary"),
      );

    expect(highlighted()).toEqual([false, false]);
    await userEvent.click(screen.getByText("Sortable"));
    expect(highlighted()).toEqual([true, false]);
    await userEvent.click(screen.getByText("Sortable"));
    expect(highlighted()).toEqual([false, true]);
  });

  it("puts the sorter and the filter after the title, not around it", () => {
    render(
      <DataTable
        columns={[
          {
            title: "Both",
            dataIndex: "name",
            key: "name",
            sorter: true,
            filters: [{ text: "a", value: "a" }],
            onFilter: () => true,
          },
        ]}
        dataSource={rows}
      />,
    );
    /*
     * The order in the DOM is what the right-hand alignment rests on: title
     * first in a flex row that grows, then the icon cluster pushed to the
     * cell's trailing edge.
     */
    const th = screen.getByText("Both").closest("th");
    const cluster = th.querySelector(".ant-table-column-sorter").parentElement;
    expect(cluster.querySelector(".ant-table-filter-trigger")).not.toBeNull();
    expect(
      screen.getByText("Both").compareDocumentPosition(cluster) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("keeps a centred sortable column's title centred", () => {
    // Three columns in the app are both aligned and sortable; antd centres the
    // title in the space the sorter leaves rather than flushing it left.
    render(
      <DataTable
        columns={[
          {
            title: "Errors",
            dataIndex: "name",
            key: "name",
            align: "center",
            sorter: true,
          },
        ]}
        dataSource={rows}
      />,
    );
    const th = screen.getByText("Errors").closest("th");
    expect(th.className).toContain("text-center");
    // The title box grows, so the inherited text-align has room to act on.
    expect(screen.getByText("Errors").className).toContain("flex-1");
  });

  it("sizes a call-site's own filter icon rather than trusting it to", () => {
    // Every filterIcon in the app is a bare lucide icon, which defaults to
    // 24px and dwarfed both the title and the carets beside it.
    render(
      <DataTable
        columns={[
          {
            title: "Filtered",
            dataIndex: "name",
            key: "name",
            filters: [{ text: "a", value: "a" }],
            filterIcon: () => <svg data-testid="custom-icon" />,
            onFilter: () => true,
          },
        ]}
        dataSource={rows}
      />,
    );
    expect(
      screen.getByTestId("custom-icon").closest(".ant-table-filter-trigger")
        .className,
    ).toContain("[&_svg]:size-3.5");
  });
});

/**
 * antd's `sortDirections`. All four Execution Logs tables pass
 * `["ascend", "descend", "ascend"]` — the idiom for "never cycle back to
 * unsorted" — and the prop was landing on the wrapper <div> instead, where
 * React warned about an unrecognised DOM attribute on every render.
 */
describe("DataTable sortDirections", () => {
  const rows = [{ id: 1, name: "a" }];
  const sortable = [
    { title: "Name", dataIndex: "name", key: "name", sorter: true },
  ];

  it("keeps cycling between ascend and descend when a direction repeats", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={sortable}
        dataSource={rows}
        sortDirections={["ascend", "descend", "ascend"]}
        onChange={onChange}
      />,
    );
    const header = screen.getByText("Name");
    await userEvent.click(header);
    await userEvent.click(header);
    await userEvent.click(header);
    // A third click returns to ascend rather than clearing the sort.
    expect(onChange.mock.calls[2][2]).toMatchObject({ order: "ascend" });
  });

  it("leaves the prop off the DOM", () => {
    const { container } = render(
      <DataTable
        columns={sortable}
        dataSource={rows}
        sortDirections={["ascend", "descend"]}
      />,
    );
    expect(
      container.querySelector("[sortdirections], [sortDirections]"),
    ).toBeNull();
  });
});

/**
 * A CONTROLLED filter column — one passing `filteredValue` — still has to
 * report the keys the user just picked, not the value its parent is currently
 * holding. Echoing `filteredValue` back is how the parent learns nothing
 * changed, which left LogModal's level filter permanently stuck.
 */
describe("DataTable controlled filters", () => {
  const rows = [{ id: 1, name: "Row 1" }];

  it("reports the newly picked keys, not the parent's stale filteredValue", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          {
            title: "Level",
            dataIndex: "name",
            key: "level",
            // The parent holds "no level selected" while the user picks ERROR.
            filteredValue: [],
            filterDropdown: ({ setSelectedKeys, confirm }) => (
              <button
                type="button"
                onClick={() => {
                  setSelectedKeys(["ERROR"]);
                  confirm();
                }}
              >
                Pick ERROR
              </button>
            ),
          },
        ]}
        dataSource={rows}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Filter by Level"));
    await userEvent.click(screen.getByRole("button", { name: "Pick ERROR" }));
    expect(onChange.mock.calls[0][1]).toEqual({ level: ["ERROR"] });
  });

  it("drives the parent's state through a full controlled round trip", async () => {
    function Harness() {
      const [level, setLevel] = useState(null);
      return (
        <>
          <span data-testid="level">{level ?? "none"}</span>
          <DataTable
            columns={[
              {
                title: "Level",
                dataIndex: "name",
                key: "level",
                filteredValue: level ? [level] : [],
                filterDropdown: ({ setSelectedKeys, confirm }) => (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedKeys(["ERROR"]);
                      confirm();
                    }}
                  >
                    Pick ERROR
                  </button>
                ),
              },
            ]}
            dataSource={rows}
            onChange={(_p, filters) => setLevel(filters.level[0] ?? null)}
          />
        </>
      );
    }
    render(<Harness />);
    await userEvent.click(screen.getByLabelText("Filter by Level"));
    await userEvent.click(screen.getByRole("button", { name: "Pick ERROR" }));
    expect(screen.getByTestId("level")).toHaveTextContent("ERROR");
  });

  it("leaves the other columns' reported values alone", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          {
            title: "Level",
            dataIndex: "name",
            key: "level",
            filteredValue: ["INFO"],
            filterDropdown: <div />,
          },
          {
            title: "Stage",
            dataIndex: "name",
            key: "stage",
            filters: [{ text: "RUN", value: "RUN" }],
            filterDropdown: ({ setSelectedKeys, confirm }) => (
              <button
                type="button"
                onClick={() => {
                  setSelectedKeys(["RUN"]);
                  confirm();
                }}
              >
                Pick RUN
              </button>
            ),
          },
        ]}
        dataSource={rows}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Filter by Stage"));
    await userEvent.click(screen.getByRole("button", { name: "Pick RUN" }));
    expect(onChange.mock.calls[0][1]).toEqual({
      level: ["INFO"],
      stage: ["RUN"],
    });
  });
});

/**
 * antd's `dataIndex` is either a key or a PATH — `["product", "name"]` reads
 * `record.product.name`. The flat lookup this guards indexed the record with
 * the array itself, which JavaScript stringifies to the property name
 * `"product,name"`, so the value was always undefined and — because a column
 * with no `render` hands it straight to the cell — silently blank.
 *
 * LLMWhisperer's API Keys table declares its Plan column exactly this way and
 * lost the whole column to an empty strip after the migration.
 */
describe("DataTable nested dataIndex", () => {
  const nested = [
    { id: 1, product: { id: "free", name: "LLM Whisperer Free" } },
  ];

  it("resolves an array dataIndex as a path into the record", () => {
    render(
      <DataTable
        columns={[
          {
            title: "Plan",
            dataIndex: ["product", "name"],
            key: "product_name",
          },
        ]}
        dataSource={nested}
        rowKey="id"
      />,
    );
    expect(screen.getByText("LLM Whisperer Free")).toBeInTheDocument();
  });

  it("renders an empty cell rather than throwing on a missing segment", () => {
    expect(() =>
      render(
        <DataTable
          columns={[
            {
              title: "Plan",
              dataIndex: ["product", "name"],
              key: "product_name",
            },
          ]}
          dataSource={[{ id: 1, product: null }, { id: 2 }]}
          rowKey="id"
        />,
      ),
    ).not.toThrow();
    // Two rows, both with an EMPTY Plan cell — not the empty state, and not a
    // stand-in like "undefined" or "N/A" that a laxer resolver would print.
    const cells = document.querySelectorAll("tbody td");
    expect(cells).toHaveLength(2);
    for (const cell of cells) {
      expect(cell).toHaveTextContent("");
    }
  });

  it("walks a path of any depth, including an array index", () => {
    render(
      <DataTable
        columns={[
          {
            title: "Owner",
            dataIndex: ["subscription", "owners", 0, "email"],
            key: "owner",
          },
        ]}
        dataSource={[
          { id: 1, subscription: { owners: [{ email: "a@example.com" }] } },
        ]}
        rowKey="id"
      />,
    );
    expect(screen.getByText("a@example.com")).toBeInTheDocument();
  });

  /*
   * The identity a nested column reports back through antd's `onChange`.
   *
   * With no `key`, the column id and `toSorterInfo`'s lookup both coerce the
   * array to `"product,name"` — agreeing only because NEITHER normalises it.
   * Normalising the id alone (to `"product.name"`, say) is exactly the tidy-up
   * a later reader would attempt, and it would silently stop a nested column
   * reporting its sort, with every other test here still green.
   */
  it("reports a keyless nested column through onChange when sorted", async () => {
    const onChange = vi.fn();
    render(
      <DataTable
        columns={[
          { title: "Plan", dataIndex: ["product", "name"], sorter: true },
        ]}
        dataSource={nested}
        rowKey="id"
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByText("Plan"));
    expect(onChange).toHaveBeenCalled();
    const sorter = onChange.mock.calls.at(-1)[2];
    expect(sorter.field).toEqual(["product", "name"]);
    expect(sorter.order).toBe("ascend");
  });

  it("hands the resolved nested value to render, as antd does", () => {
    const renderCell = vi.fn((value) => `plan: ${value}`);
    render(
      <DataTable
        columns={[
          {
            title: "Plan",
            dataIndex: ["product", "name"],
            key: "product_name",
            render: renderCell,
          },
        ]}
        dataSource={nested}
        rowKey="id"
      />,
    );
    expect(renderCell).toHaveBeenCalledWith("LLM Whisperer Free", nested[0], 0);
    expect(screen.getByText("plan: LLM Whisperer Free")).toBeInTheDocument();
  });
});
