import { Filter } from "lucide-react";
import PropTypes from "prop-types";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/**
 * antd's per-column filter affordance: the little icon in the header and the
 * panel it opens.
 *
 * `DataTable` presents antd's `Table` API, but every filter prop on a column —
 * `filters`, `filterDropdown`, `filterIcon`, `onFilter`, `filteredValue` — was
 * dropped on the floor, so the header rendered the bare title. The visible
 * casualties were the Execution Logs screens: the Execution ID search, the file
 * name search and the Status filter all vanished from a page whose whole
 * purpose is finding one execution among thousands.
 *
 * Two shapes, both in use here:
 *
 *  - `filterDropdown` — the call-site renders the whole panel. It may be a
 *    node (LogsTable's execution-ID box, which owns its own state and never
 *    calls back) or a function given antd's render props.
 *  - `filters` — a list of `{ text, value }`; this file renders antd's own
 *    checkbox menu with the Reset/OK footer under it.
 */

/** antd's column identity: `key`, else `dataIndex`. */
function columnKey(column) {
  return String(column.key ?? column.dataIndex);
}

/** A string for `aria-label` even when `title` is a node. */
function columnLabel(column) {
  return typeof column.title === "string" ? column.title : columnKey(column);
}

/** The built-in `filters` menu: a checkbox (or radio) per option. */
function FilterMenu({ options, filterSearch, multiple, draft, onDraftChange }) {
  const [query, setQuery] = React.useState("");

  const visible = query
    ? options.filter((o) =>
        String(o.text).toLowerCase().includes(query.toLowerCase()),
      )
    : options;

  const toggle = (value) => {
    if (!multiple) {
      // antd's `filterMultiple: false` is a radio group: picking one option
      // replaces the selection rather than adding to it.
      onDraftChange(draft.includes(value) ? [] : [value]);
      return;
    }
    onDraftChange(
      draft.includes(value)
        ? draft.filter((v) => v !== value)
        : [...draft, value],
    );
  };

  return (
    <div className="max-h-64 overflow-y-auto py-1">
      {filterSearch ? (
        <div className="px-2 pb-1">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search in filters"
            className="h-7 text-xs"
          />
        </div>
      ) : null}
      {visible.length === 0 ? (
        <div className="px-3 py-2 text-xs text-muted-foreground">
          No filters
        </div>
      ) : null}
      {visible.map((option) => (
        <label
          // Values are raw — `filters` legitimately carries booleans (Manual
          // Review's In Review / Pending) — so only the React key is stringly.
          key={String(option.value)}
          className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted"
        >
          <Checkbox
            checked={draft.includes(option.value)}
            onCheckedChange={() => toggle(option.value)}
            className={cn(!multiple && "rounded-full")}
          />
          <span className="truncate">{option.text}</span>
        </label>
      ))}
    </div>
  );
}

FilterMenu.propTypes = {
  options: PropTypes.array.isRequired,
  filterSearch: PropTypes.bool,
  multiple: PropTypes.bool,
  draft: PropTypes.array.isRequired,
  onDraftChange: PropTypes.func.isRequired,
};

/**
 * The header trigger plus its panel.
 *
 * `selectedKeys` is the COMMITTED filter — what the table is filtered by right
 * now. The panel edits a draft and only publishes it through `onConfirm`, which
 * is what makes antd's Reset/OK footer mean anything.
 */
function ColumnFilter({ column, selectedKeys, onConfirm }) {
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState(selectedKeys);
  /*
   * The draft lives in a ref as well as in state because antd's render props
   * are routinely called back-to-back in one handler — LogModal's level filter
   * does `setSelectedKeys([level]); confirm();` — and `confirm` has to publish
   * the keys that were just set, not the ones React has yet to re-render with.
   */
  const draftRef = React.useRef(selectedKeys);

  const setSelectedKeys = (keys) => {
    draftRef.current = keys ?? [];
    setDraft(draftRef.current);
  };

  const confirm = (options) => {
    onConfirm(draftRef.current);
    // antd's `confirm({ closeDropdown: false })` commits but leaves the panel up.
    if (options?.closeDropdown !== false) {
      setOpen(false);
    }
  };

  // antd's `clearFilters` publishes the empty selection and, by default, leaves
  // the panel open so the user can pick something else.
  const clearFilters = () => {
    draftRef.current = [];
    setDraft([]);
    onConfirm([]);
  };

  const handleOpenChange = (next) => {
    if (next) {
      // Re-seed on open: a panel dismissed with Escape must not carry its
      // abandoned draft into the next visit.
      draftRef.current = selectedKeys;
      setDraft(selectedKeys);
    }
    setOpen(next);
  };

  const filtered = selectedKeys.length > 0;

  const icon =
    typeof column.filterIcon === "function"
      ? column.filterIcon(filtered)
      : (column.filterIcon ?? <Filter className="size-3" />);

  let panel;
  if (column.filterDropdown) {
    panel =
      typeof column.filterDropdown === "function"
        ? column.filterDropdown({
            prefixCls: "ant-table-filter-dropdown",
            setSelectedKeys,
            selectedKeys: draft,
            confirm,
            clearFilters,
            filters: column.filters,
            visible: open,
            close: () => setOpen(false),
          })
        : column.filterDropdown;
  } else {
    const multiple = column.filterMultiple !== false;
    panel = (
      <>
        <FilterMenu
          options={column.filters ?? []}
          filterSearch={Boolean(column.filterSearch)}
          multiple={multiple}
          draft={draft}
          onDraftChange={setSelectedKeys}
        />
        <div className="flex items-center justify-between border-t border-separator px-2 py-1.5">
          <Button
            variant="link"
            size="sm"
            className="h-6 px-1"
            disabled={draft.length === 0}
            onClick={clearFilters}
          >
            Reset
          </Button>
          <Button size="sm" className="h-6" onClick={() => confirm()}>
            OK
          </Button>
        </div>
      </>
    );
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Filter by ${columnLabel(column)}`}
          aria-expanded={open}
          data-filtered={filtered ? "true" : undefined}
          className={cn(
            "ant-table-filter-trigger inline-flex cursor-pointer items-center rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground",
            /*
             * The trigger sizes its icon rather than trusting the call site to,
             * exactly as antd does (`.ant-table-filter-trigger .anticon` is a
             * 12px font-size). Every custom `filterIcon` in the app — the two
             * Search boxes and the two Filter menus — is a bare lucide icon, so
             * all four came out at lucide's 24px default and towered over both
             * the header text and the sort carets beside them.
             */
            "[&_svg]:size-3.5",
            filtered && "active text-primary hover:text-primary",
          )}
          /*
           * The <th> carries the sort handler, so without this a click on the
           * filter icon would also re-sort the column underneath the panel.
           * `stopPropagation` leaves `defaultPrevented` alone, so Radix still
           * gets its own click through and opens the popover.
           */
          onClick={(event) => event.stopPropagation()}
        >
          {icon}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="ant-table-filter-dropdown w-auto min-w-[160px] max-w-xs p-0 font-normal"
        // A custom `filterDropdown` is usually a search box the user is about
        // to type in; antd focuses it, and stealing focus back to the trigger
        // would undo that.
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        {panel}
      </PopoverContent>
    </Popover>
  );
}

ColumnFilter.propTypes = {
  column: PropTypes.object.isRequired,
  selectedKeys: PropTypes.array.isRequired,
  onConfirm: PropTypes.func.isRequired,
};

export { ColumnFilter, columnKey };
