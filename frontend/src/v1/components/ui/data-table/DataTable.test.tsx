import { act, fireEvent, screen, within } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "./DataTable";
import {
  GALLERY_COLUMNS,
  type GalleryDeployment,
  galleryRows,
  rowActions,
  rowId,
  rowLabel,
  rowTone,
} from "./data-table.gallery";
import type { DataTableColumn, DataTableProps } from "./types";

type Props = Partial<DataTableProps<GalleryDeployment>>;

const FIVE = galleryRows(5);

function setup(props: Props = {}) {
  return renderV1(
    <DataTable
      label="API deployments"
      columns={GALLERY_COLUMNS}
      rows={FIVE}
      getRowId={rowId}
      getRowLabel={rowLabel}
      {...props}
    />,
  );
}

const table = () => screen.getByRole("table", { name: "API deployments" });
const bodyRows = () => [
  ...table().querySelectorAll<HTMLTableRowElement>(
    "[data-slot=data-table-row]",
  ),
];
/** The first data cell's text of each row, in order. */
const names = () =>
  bodyRows().map((row) => row.querySelector(".ui\\:font-medium")?.textContent);
const status = () =>
  document.querySelector("[data-slot=data-table-status]")?.textContent?.trim();
const header = (name: string) => screen.getByRole("columnheader", { name });
const sortButton = (name: string) =>
  within(header(name)).getByRole("button", { name });

/**
 * A screen of `width` pixels for the priority media queries, and `resize` to
 * cross a breakpoint (fires the queries' change listeners). Any other query
 * (the theme's prefers-color-scheme) does not match.
 */
function stubScreen(width: number) {
  let current = width;
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", (query: string) => {
    const min = /min-width: (\d+)px/.exec(query);
    return {
      media: query,
      get matches() {
        return min !== null && current >= Number(min[1]);
      },
      addEventListener: (_: string, cb: () => void) => {
        if (min !== null) {
          listeners.add(cb);
        }
      },
      removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
      onchange: null,
      dispatchEvent: () => true,
    };
  });
  return {
    resize(next: number) {
      current = next;
      act(() => {
        for (const cb of listeners) {
          cb();
        }
      });
    },
  };
}

const headers = () =>
  screen.getAllByRole("columnheader").map((th) => th.textContent?.trim());

describe("sorting", () => {
  it("cycles a header through ascending, descending and off, and announces each", async () => {
    const onSortChange = vi.fn();
    const { user } = setup({ onSortChange });
    const original = names();

    await user.click(sortButton("Name"));
    expect(header("Name").getAttribute("aria-sort")).toBe("ascending");
    expect(names()).toEqual(
      [...original].sort((a, b) =>
        (a ?? "").localeCompare(b ?? "", undefined, {
          sensitivity: "base",
          numeric: true,
        }),
      ),
    );
    expect(status()).toBe("Sorted by Name, ascending");
    expect(onSortChange).toHaveBeenLastCalledWith({
      columnId: "name",
      direction: "asc",
    });

    await user.click(sortButton("Name"));
    expect(header("Name").getAttribute("aria-sort")).toBe("descending");
    expect(names()[0]).toBe("UCC_Formatting API");
    expect(status()).toBe("Sorted by Name, descending");

    await user.click(sortButton("Name"));
    expect(header("Name").hasAttribute("aria-sort")).toBe(false);
    expect(names()).toEqual(original);
    expect(status()).toBe("Sort cleared");
    expect(onSortChange).toHaveBeenLastCalledWith(null);
  });

  it("sorts one column at a time: a new column replaces the old sort", async () => {
    const { user } = setup();
    await user.click(sortButton("Name"));
    await user.click(sortButton("Owner"));
    expect(header("Name").hasAttribute("aria-sort")).toBe(false);
    expect(header("Owner").getAttribute("aria-sort")).toBe("ascending");
    expect(
      screen
        .getAllByRole("columnheader")
        .filter((th) => th.hasAttribute("aria-sort")),
    ).toHaveLength(1);
  });

  it("sorts on Enter from the header", async () => {
    const { user } = setup();
    sortButton("Last run").focus();
    await user.keyboard("{Enter}");
    expect(header("Last run").getAttribute("aria-sort")).toBe("ascending");
    const days = bodyRows().map((row) => row.textContent);
    expect(days[0]).toContain("Aug 01");
  });

  it("orders numbers by value and puts missing values last both ways", async () => {
    type R = { id: string; n: number | null };
    const rows: R[] = [
      { id: "a", n: 10 },
      { id: "b", n: null },
      { id: "c", n: 9 },
      { id: "d", n: 100 },
    ];
    const columns: DataTableColumn<R>[] = [
      {
        id: "n",
        header: "Count",
        sortKey: (r) => r.n,
        cell: (r) => <b>{r.id}</b>,
      },
    ];
    const { user } = renderV1(
      <DataTable
        label="Counts"
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        getRowLabel={(r) => r.id}
      />,
    );
    const order = () =>
      [...document.querySelectorAll("tbody b")].map((b) => b.textContent);
    await user.click(screen.getByRole("button", { name: "Count" }));
    expect(order()).toEqual(["c", "a", "d", "b"]);
    await user.click(screen.getByRole("button", { name: "Count" }));
    expect(order()).toEqual(["d", "a", "c", "b"]);
  });

  it("leaves rows in the given order with server pagination, and only reports the sort", async () => {
    const onSortChange = vi.fn();
    const { user } = setup({
      onSortChange,
      pagination: {
        mode: "server",
        page: 1,
        pageSize: 5,
        total: 5,
        onPageChange: vi.fn(),
      },
    });
    const original = names();
    await user.click(sortButton("Name"));
    expect(onSortChange).toHaveBeenCalledWith({
      columnId: "name",
      direction: "asc",
    });
    expect(names()).toEqual(original);
    expect(header("Name").getAttribute("aria-sort")).toBe("ascending");
  });

  it("follows a controlled sort and does not change it itself", async () => {
    const onSortChange = vi.fn();
    const { user, rerender } = setup({
      sort: { columnId: "owner", direction: "desc" },
      onSortChange,
    });
    expect(header("Owner").getAttribute("aria-sort")).toBe("descending");
    await user.click(sortButton("Name"));
    expect(onSortChange).toHaveBeenCalledWith({
      columnId: "name",
      direction: "asc",
    });
    expect(header("Owner").getAttribute("aria-sort")).toBe("descending");
    rerender(
      <DataTable
        label="API deployments"
        columns={GALLERY_COLUMNS}
        rows={FIVE}
        getRowId={rowId}
        getRowLabel={rowLabel}
        sort={null}
      />,
    );
    expect(header("Owner").hasAttribute("aria-sort")).toBe(false);
  });

  it("draws a column without a sort key as plain text", () => {
    setup({ columns: [{ id: "x", header: "Plain", cell: () => "x" }] });
    expect(within(header("Plain")).queryByRole("button")).toBeNull();
  });
});

describe("selection and the bulk bar", () => {
  const checkbox = (name: string) => screen.getByRole("checkbox", { name });
  const all = () => checkbox("Select all rows on this page");

  it("selects rows, shows the mixed then checked header box, and announces the count", async () => {
    const bulk = vi.fn(() => <button type="button">Delete selected</button>);
    const { user } = setup({ selectable: true, bulkActions: bulk });
    expect(all().getAttribute("aria-checked")).toBe("false");
    expect(screen.queryByRole("region", { name: "Bulk actions" })).toBeNull();

    await user.click(checkbox("Select masa_cms"));
    expect(all().getAttribute("aria-checked")).toBe("mixed");
    expect(status()).toBe("1 row selected");
    const bar = screen.getByRole("region", { name: "Bulk actions" });
    expect(bar.textContent).toContain("1 selected");
    expect(bulk).toHaveBeenLastCalledWith(
      expect.objectContaining({
        selectedIds: ["dep-3"],
        selectedRows: [FIVE[2]],
      }),
    );
    expect(bodyRows()[2].getAttribute("data-state")).toBe("selected");
    expect(bodyRows()[0].hasAttribute("data-state")).toBe(false);

    await user.click(checkbox("Select masa_eob_extraction"));
    expect(status()).toBe("2 rows selected");

    await user.click(all());
    expect(all().getAttribute("aria-checked")).toBe("true");
    expect(status()).toBe("All 5 rows on this page selected, 5 in total");

    await user.click(all());
    expect(all().getAttribute("aria-checked")).toBe("false");
    expect(status()).toBe("Selection cleared");
    expect(screen.queryByRole("region", { name: "Bulk actions" })).toBeNull();
  });

  it("clears from the bulk bar and from the bulk action's context", async () => {
    const { user } = setup({
      selectable: true,
      defaultSelectedIds: ["dep-1", "dep-2"],
      bulkActions: ({ clearSelection }) => (
        <button type="button" onClick={clearSelection}>
          Abort selected
        </button>
      ),
    });
    expect(
      screen.getByRole("region", { name: "Bulk actions" }).textContent,
    ).toContain("2 selected");
    await user.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.queryByRole("region", { name: "Bulk actions" })).toBeNull();
    expect(status()).toBe("Selection cleared");
  });

  it("selects the focused row on Space, and Shift+Tab reaches the bulk bar", async () => {
    const { user } = setup({
      selectable: true,
      bulkActions: () => <button type="button">Abort selected</button>,
    });
    bodyRows()[0].focus();
    await user.keyboard(" ");
    expect(
      checkbox("Select health-monitoring API").getAttribute("aria-checked"),
    ).toBe("true");
    expect(status()).toBe("1 row selected");
    await user.keyboard(" ");
    expect(
      checkbox("Select health-monitoring API").getAttribute("aria-checked"),
    ).toBe("false");
    await user.keyboard(" ");

    // Back out of the table: row → sort buttons → header box → bulk bar.
    for (
      let i = 0;
      i < 12 &&
      !screen
        .getByRole("region", { name: "Bulk actions" })
        .contains(document.activeElement);
      i++
    ) {
      await user.tab({ shift: true });
    }
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Abort selected" }),
    );
  });

  it("reports a controlled selection and draws what the parent passes", async () => {
    const onSelectionChange = vi.fn();
    const { user } = setup({
      selectable: true,
      selectedIds: ["dep-5"],
      onSelectionChange,
    });
    expect(
      checkbox("Select UCC_Formatting API").getAttribute("aria-checked"),
    ).toBe("true");
    await user.click(checkbox("Select masa_cms"));
    expect(onSelectionChange).toHaveBeenCalledWith(["dep-5", "dep-3"]);
    // Still the parent's selection until it passes a new one.
    expect(checkbox("Select masa_cms").getAttribute("aria-checked")).toBe(
      "false",
    );
  });

  it("selects the page, not every row, with client pagination; the count spans pages", async () => {
    const { user } = setup({
      rows: galleryRows(12),
      selectable: true,
      pagination: { mode: "client", pageSize: 5 },
    });
    await user.click(all());
    expect(status()).toBe("All 5 rows on this page selected, 5 in total");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(all().getAttribute("aria-checked")).toBe("false");
    await user.click(checkbox("Select invoice-parser"));
    expect(
      screen.getByRole("region", { name: "Bulk actions" }).textContent,
    ).toContain("6 selected");
  });
});

describe("expansion", () => {
  const detail = (row: GalleryDeployment) => <p>Detail of {row.name}</p>;

  it("opens a row in place under it, tied by aria-controls", async () => {
    const { user } = setup({ renderExpanded: detail });
    const toggle = screen.getByRole("button", { name: "Details for masa_cms" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const panel = document.getElementById(
      toggle.getAttribute("aria-controls") ?? "",
    );
    expect(panel?.textContent).toBe("Detail of masa_cms");
    // Directly under its row.
    expect(bodyRows()[2].nextElementSibling?.contains(panel ?? null)).toBe(
      true,
    );
    await user.click(toggle);
    expect(screen.queryByText("Detail of masa_cms")).toBeNull();
  });

  it("opens with Right and Enter and closes with Left from the focused row", async () => {
    const { user } = setup({ renderExpanded: detail });
    bodyRows()[1].focus();
    await user.keyboard("{ArrowRight}");
    expect(
      screen.getByText("Detail of API Hub - Purchase Order API"),
    ).toBeTruthy();
    await user.keyboard("{ArrowLeft}");
    expect(
      screen.queryByText("Detail of API Hub - Purchase Order API"),
    ).toBeNull();
    await user.keyboard("{Enter}");
    expect(
      screen.getByText("Detail of API Hub - Purchase Order API"),
    ).toBeTruthy();
  });

  it("gives no toggle to a row that cannot expand", () => {
    setup({ renderExpanded: detail, canExpand: (row) => row.id !== "dep-2" });
    expect(
      screen.queryByRole("button", {
        name: "Details for API Hub - Purchase Order API",
      }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "Details for masa_cms" }),
    ).toBeTruthy();
  });

  it("starts with the given rows open", () => {
    setup({ renderExpanded: detail, defaultExpandedIds: ["dep-4"] });
    expect(screen.getByText("Detail of masa_eob_extraction")).toBeTruthy();
  });
});

describe("row click target, actions and keyboard focus", () => {
  it("fires on a click anywhere on the row and on Enter, but not from its controls", async () => {
    const onRowClick = vi.fn();
    const { user } = setup({ onRowClick, selectable: true, rowActions });
    await user.click(screen.getByText("masa_cms"));
    expect(onRowClick).toHaveBeenCalledWith(FIVE[2]);
    onRowClick.mockClear();

    await user.click(screen.getByRole("checkbox", { name: "Select masa_cms" }));
    await user.click(
      screen.getByRole("button", { name: "Actions for masa_cms" }),
    );
    expect(onRowClick).not.toHaveBeenCalled();
    await user.keyboard("{Escape}");

    bodyRows()[3].focus();
    await user.keyboard("{Enter}");
    expect(onRowClick).toHaveBeenCalledWith(FIVE[3]);
  });

  it("keeps one row in the tab order and moves it with the arrows, Home and End", async () => {
    const { user } = setup({ onRowClick: vi.fn(), rowActions });
    const tabbable = () => bodyRows().filter((row) => row.tabIndex === 0);
    expect(tabbable()).toEqual([bodyRows()[0]]);
    bodyRows()[0].focus();
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(bodyRows()[1]);
    expect(tabbable()).toEqual([bodyRows()[1]]);
    await user.keyboard("{End}");
    expect(document.activeElement).toBe(bodyRows()[4]);
    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(bodyRows()[4]);
    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(bodyRows()[0]);
    await user.keyboard("{ArrowUp}");
    expect(document.activeElement).toBe(bodyRows()[0]);

    // Controls of other rows leave the tab order.
    expect(
      screen.getByRole("button", { name: "Actions for health-monitoring API" })
        .tabIndex,
    ).toBe(0);
    expect(
      screen.getByRole("button", { name: "Actions for masa_cms" }).tabIndex,
    ).toBe(-1);
    // Tab from the active row goes to its own kebab.
    await user.tab();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Actions for health-monitoring API" }),
    );
  });

  it("makes the row whose control takes focus the active row", async () => {
    const { user } = setup({ selectable: true });
    await user.click(screen.getByRole("checkbox", { name: "Select masa_cms" }));
    expect(bodyRows()[2].tabIndex).toBe(0);
    expect(bodyRows()[0].tabIndex).toBe(-1);
  });

  it("leaves plain rows out of the tab order", () => {
    setup();
    expect(bodyRows().every((row) => !row.hasAttribute("tabindex"))).toBe(true);
  });

  it("opens the row menu with destructive actions last, and runs the chosen one", async () => {
    const onEdit = vi.fn();
    const { user } = setup({
      rowActions: () => [
        { id: "delete", label: "Delete", destructive: true, onSelect: vi.fn() },
        { id: "edit", label: "Edit", onSelect: onEdit },
        { id: "off", label: "Disable", disabled: true, onSelect: vi.fn() },
      ],
    });
    await user.click(
      screen.getByRole("button", { name: "Actions for masa_cms" }),
    );
    const items = screen
      .getAllByRole("menuitem")
      .map((item) => item.textContent);
    expect(items).toEqual(["Edit", "Disable", "Delete"]);
    expect(screen.getByRole("separator")).toBeTruthy();
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalledOnce();
  });

  it("disables the kebab of a row with no actions", () => {
    setup({ rowActions: () => [] });
    expect(
      (
        screen.getByRole("button", {
          name: "Actions for masa_cms",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("marks failed rows with the failure tone", () => {
    setup({ getRowTone: rowTone });
    expect(bodyRows().map((row) => row.getAttribute("data-tone"))).toEqual([
      null,
      "failure",
      null,
      null,
      null,
    ]);
  });
});

describe("column priority", () => {
  it.each([
    [768, ["Name", "Last run"]],
    [1024, ["Name", "Owner", "Last run"]],
    [1280, ["Name", "Workflow", "Owner", "Last run"]],
    [1440, ["Name", "Workflow", "Owner", "Last run", "Total runs"]],
  ])("at %ipx shows %j", (width, expected) => {
    stubScreen(width);
    setup();
    expect(headers()).toEqual(expected);
    expect(bodyRows()[0].cells).toHaveLength(expected.length);
  });

  it("drops and restores columns as the screen crosses a breakpoint", () => {
    const screenSize = stubScreen(1440);
    setup();
    expect(headers()).toContain("Total runs");
    screenSize.resize(1100);
    expect(headers()).toEqual(["Name", "Owner", "Last run"]);
    screenSize.resize(1500);
    expect(headers()).toContain("Total runs");
  });

  it("keeps a sort on a column it drops", async () => {
    stubScreen(768);
    setup({ defaultSort: { columnId: "totalRuns", direction: "desc" } });
    const runs = FIVE.map((row) => row.totalRuns).sort((a, b) => b - a);
    const byRuns = FIVE.slice()
      .sort((a, b) => b.totalRuns - a.totalRuns)
      .map((row) => row.name);
    expect(runs[0]).toBeGreaterThan(runs[4]);
    expect(names()).toEqual(byRuns);
  });
});

describe("states", () => {
  it("shows skeleton rows and a loading status while loading", () => {
    setup({ loading: true, selectable: true });
    expect(screen.getByText("Loading API deployments")).toBeTruthy();
    const skeleton = document.querySelector("[data-slot=data-table-skeleton]");
    expect(skeleton?.querySelectorAll("tr")).toHaveLength(5);
    expect(bodyRows()).toHaveLength(0);
    expect(
      screen
        .getByRole("checkbox", { name: "Select all rows on this page" })
        .hasAttribute("disabled"),
    ).toBe(true);
  });

  it("matches the skeleton to the page size, at most ten rows", () => {
    setup({ loading: true, pagination: { mode: "client", pageSize: 25 } });
    expect(
      document.querySelectorAll("[data-slot=data-table-skeleton] tr"),
    ).toHaveLength(10);
  });

  it("shows the empty slot with no rows, and the no-results slot while filtered", () => {
    const { rerender } = setup({ rows: [], empty: <p>No deployments yet</p> });
    expect(screen.getByText("No deployments yet")).toBeTruthy();
    rerender(
      <DataTable
        label="API deployments"
        columns={GALLERY_COLUMNS}
        rows={[]}
        getRowId={rowId}
        getRowLabel={rowLabel}
        filtered
        noResults={<p>Nothing matches</p>}
        empty={<p>No deployments yet</p>}
      />,
    );
    expect(screen.getByText("Nothing matches")).toBeTruthy();
    expect(screen.queryByText("No deployments yet")).toBeNull();
  });

  it("falls back to default empty and no-results text", () => {
    const { rerender } = setup({ rows: [] });
    expect(screen.getByText("Nothing here yet.")).toBeTruthy();
    rerender(
      <DataTable
        label="API deployments"
        columns={GALLERY_COLUMNS}
        rows={[]}
        getRowId={rowId}
        getRowLabel={rowLabel}
        filtered
      />,
    );
    expect(
      screen.getByText("No results match your search or filters."),
    ).toBeTruthy();
  });

  it("shows an error above the rows with a retry, and no empty state under it", async () => {
    const onRetry = vi.fn();
    const { user, rerender } = setup({
      error: { title: "Could not load", message: "Timed out", onRetry },
    });
    expect(screen.getByRole("alert").textContent).toContain("Could not load");
    expect(bodyRows()).toHaveLength(5);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
    rerender(
      <DataTable
        label="API deployments"
        columns={GALLERY_COLUMNS}
        rows={[]}
        getRowId={rowId}
        getRowLabel={rowLabel}
        error={{ title: "Could not load" }}
      />,
    );
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
  });

  it("renders the toolbar and footer slots", () => {
    setup({
      toolbar: <input aria-label="Search deployments" />,
      footer: "Updated 2 min ago",
    });
    expect(
      screen.getByRole("textbox", { name: "Search deployments" }),
    ).toBeTruthy();
    expect(
      document.querySelector("[data-slot=data-table-footer]")?.textContent,
    ).toContain("Updated 2 min ago");
  });
});

describe("pagination", () => {
  it("settles after rendering a client-paged table and after a breakpoint", async () => {
    // TanStack's auto-reset once re-rendered a client-paged table forever.
    const cell = vi.fn((row: GalleryDeployment) => row.name);
    const screenSize = stubScreen(1440);
    setup({
      rows: galleryRows(30),
      columns: [{ id: "name", header: "Name", sortKey: "name", cell }],
      pagination: { mode: "client", pageSize: 10 },
    });
    const settle = () =>
      act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 30));
      });
    await settle();
    const afterMount = cell.mock.calls.length;
    await settle();
    expect(cell.mock.calls.length).toBe(afterMount);
    screenSize.resize(900);
    await settle();
    const afterResize = cell.mock.calls.length;
    expect(afterResize - afterMount).toBeLessThanOrEqual(20);
    await settle();
    expect(cell.mock.calls.length).toBe(afterResize);
  });

  it("pages the rows on the client, and a sort goes back to page 1", async () => {
    const { user } = setup({
      rows: galleryRows(30),
      pagination: { mode: "client", pageSize: 10 },
    });
    expect(bodyRows()).toHaveLength(10);
    expect(screen.getByText("Showing 1 to 10 of 30 entries")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Showing 11 to 20 of 30 entries")).toBeTruthy();
    expect(names()[0]).toBe("masa_eob_extraction 2");
    await user.click(sortButton("Name"));
    expect(screen.getByText("Showing 1 to 10 of 30 entries")).toBeTruthy();
  });

  it("changes the client page size", async () => {
    const { user } = setup({
      rows: galleryRows(30),
      pagination: { mode: "client", pageSize: 10 },
    });
    await user.selectOptions(screen.getByLabelText("Rows per page"), "20");
    expect(bodyRows()).toHaveLength(20);
  });

  it("asks the parent for another page with server pagination", async () => {
    const onPageChange = vi.fn();
    const { user } = setup({
      pagination: {
        mode: "server",
        page: 2,
        pageSize: 5,
        total: 333,
        onPageChange,
      },
    });
    expect(bodyRows()).toHaveLength(5);
    expect(screen.getByText("Showing 6 to 10 of 333 entries")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });
});

describe("1,000 rows", () => {
  const THOUSAND = galleryRows(1000);
  function setupLarge(props: Props = {}) {
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(560);
    return setup({
      rows: THOUSAND,
      scroll: "container",
      selectable: true,
      onRowClick: vi.fn(),
      ...props,
    });
  }

  it("renders only the rows in view and tells assistive technology the full count", () => {
    setupLarge();
    expect(bodyRows().length).toBeGreaterThan(5);
    expect(bodyRows().length).toBeLessThan(40);
    expect(table().getAttribute("aria-rowcount")).toBe("1001");
    expect(bodyRows()[0].getAttribute("aria-rowindex")).toBe("2");
  });

  it("does not window a page-scrolled table", () => {
    setup({ rows: galleryRows(80) });
    expect(bodyRows()).toHaveLength(80);
    expect(table().hasAttribute("aria-rowcount")).toBe(false);
  });

  it("sorts all 1,000, not just the rows in view", async () => {
    const { user } = setupLarge();
    await user.click(sortButton("Last run"));
    await user.click(sortButton("Last run"));
    expect(bodyRows()[0].textContent).toContain("Aug 31");
    expect(status()).toBe("Sorted by Last run, descending");
  });

  it("selects all rows from the header box and scrolls to the last row on End", async () => {
    const { user } = setupLarge();
    await user.click(
      screen.getByRole("checkbox", { name: "Select all rows on this page" }),
    );
    expect(status()).toBe(
      "All 1,000 rows on this page selected, 1,000 in total",
    );
    bodyRows()[0].focus();
    const frame = document.querySelector<HTMLElement>(
      "[data-slot=data-table-frame]",
    );
    const scrollTo = vi.spyOn(HTMLElement.prototype, "scrollTo");
    await user.keyboard("{End}");
    // The table asked to scroll; happy-dom does not, so do what a browser would.
    expect(scrollTo).toHaveBeenCalled();
    expect(bodyRows().at(-1)?.textContent).not.toContain(THOUSAND[999].name);
    (frame as HTMLElement).scrollTop = 1000 * 56 - 560;
    fireEvent.scroll(frame as HTMLElement);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    const last = bodyRows().at(-1);
    expect(last?.textContent).toContain(THOUSAND[999].name);
    expect(document.activeElement).toBe(last);
  });
});
