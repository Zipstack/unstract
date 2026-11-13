import { cn } from "@v1/lib/cn";
import { SHELL_ICONS } from "@v1/lib/icons";
import {
  type JSX,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import {
  describedRowProps,
  MENU_INDICATOR_SLOT,
  MENU_LABEL,
  MENU_SEPARATOR,
  MenuCheck,
  MenuItemBody,
  type MenuItemOptions,
  menuItemClass,
} from "./item";

/*
 * A search box over a list of commands: the inside of SearchMenu and
 * CommandPalette. It follows the ARIA combobox pattern: focus stays in the
 * input, which points at the active row with `aria-activedescendant`; the
 * arrow keys move (wrapping, skipping disabled rows) and Enter runs the
 * active row. The surrounding popover or dialog handles Escape.
 */

/** One row. */
export type CommandItem = MenuItemOptions &
  Readonly<{
    /** Unique across the whole list, groups included. */
    id: string;
    label: string;
    /** Extra words the filter matches, e.g. an id or a synonym. */
    keywords?: readonly string[];
    disabled?: boolean;
    /** Shows a check before the label (a selected filter value). */
    checked?: boolean;
    /** Runs when the row is chosen, before the list's own `onSelect`. */
    onSelect?: () => void;
  }>;

/** A titled set of rows. Groups with no matching rows are hidden. */
export type CommandGroup = Readonly<{
  id: string;
  heading?: string;
  items: readonly CommandItem[];
}>;

export type CommandProps = Readonly<{
  /** The rows, in groups. For one plain list, pass `items` instead. */
  groups?: readonly CommandGroup[];
  items?: readonly CommandItem[];
  /** The search box's accessible name, e.g. "Search actions". */
  label: string;
  placeholder?: string;
  /** Controlled query. Leave out to let the list keep its own. */
  query?: string;
  onQueryChange?: (query: string) => void;
  /**
   * Default true: rows whose label or keywords do not contain the query
   * (ignoring case) are hidden. Set false when the caller filters, e.g. a
   * server search, and passes only the matching rows.
   */
  filter?: boolean;
  /** Shown when no row matches. */
  emptyText?: string;
  /** Shows "Loading…" instead of the empty text while results load. */
  loading?: boolean;
  onSelect?: (item: CommandItem) => void;
  /** A row at the bottom, below the list (key hints in the palette). */
  footer?: ReactNode;
  /** Focus the input on mount. Default true. */
  autoFocus?: boolean;
  className?: string;
  /** Classes for the scrolling list. */
  listClassName?: string;
}>;

/** Whether `item` matches `query`: a case-insensitive substring of its label or a keyword. */
export function matchesQuery(item: CommandItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === "") {
    return true;
  }
  return [item.label, ...(item.keywords ?? [])].some((text) =>
    text.toLowerCase().includes(needle),
  );
}

/** The groups left after filtering, without empty ones. */
export function filterGroups(
  groups: readonly CommandGroup[],
  query: string,
  filter: boolean,
): readonly CommandGroup[] {
  if (!filter) {
    return groups.filter((group) => group.items.length > 0);
  }
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => matchesQuery(item, query)),
    }))
    .filter((group) => group.items.length > 0);
}

/** The next enabled index from `from` in direction `step`, wrapping; -1 if none. */
export function nextEnabled(
  rows: readonly CommandItem[],
  from: number,
  step: 1 | -1,
): number {
  const count = rows.length;
  for (let offset = 1; offset <= count; offset++) {
    const index = (((from + step * offset) % count) + count) % count;
    if (!rows[index].disabled && !rows[index].loading) {
      return index;
    }
  }
  return -1;
}

const SearchIcon = SHELL_ICONS.search;

/** The search box and the list of rows. */
export function Command({
  groups,
  items,
  label,
  placeholder = "Search…",
  query: controlledQuery,
  onQueryChange,
  filter = true,
  emptyText = "No results",
  loading = false,
  onSelect,
  footer,
  autoFocus = true,
  className,
  listClassName,
}: CommandProps): JSX.Element {
  const id = useId();
  const listId = `${id}-list`;
  const [ownQuery, setOwnQuery] = useState("");
  const query = controlledQuery ?? ownQuery;
  const allGroups = useMemo(
    () => groups ?? [{ id: "items", items: items ?? [] }],
    [groups, items],
  );
  const visible = useMemo(
    () => filterGroups(allGroups, query, filter),
    [allGroups, query, filter],
  );
  const rows = useMemo(
    () => visible.flatMap((group) => group.items),
    [visible],
  );
  const [activeId, setActiveId] = useState<string | undefined>(undefined);

  // Keep the active row when it is still visible; otherwise the first enabled row.
  const activeIndex = useMemo(() => {
    const kept = rows.findIndex(
      (row) => row.id === activeId && !row.disabled && !row.loading,
    );
    return kept >= 0 ? kept : nextEnabled(rows, -1, 1);
  }, [rows, activeId]);
  const active = !loading && activeIndex >= 0 ? rows[activeIndex] : undefined;
  // DOM ids come from the row's position, not its id, which may hold spaces
  // (an IDREF cannot) or characters a selector would need escaped.
  const positions = useMemo(
    () => new Map(rows.map((row, index) => [row.id, index])),
    [rows],
  );
  const optionId = (item: CommandItem) =>
    `${id}-option-${positions.get(item.id) ?? -1}`;

  useEffect(() => {
    if (!active) {
      return;
    }
    const element = document.getElementById(`${id}-option-${activeIndex}`);
    // happy-dom and older browsers have no scrollIntoView on every element.
    element?.scrollIntoView?.({ block: "nearest" });
  }, [active, activeIndex, id]);

  const setQuery = (next: string) => {
    if (controlledQuery === undefined) {
      setOwnQuery(next);
    }
    onQueryChange?.(next);
    setActiveId(undefined);
  };

  const choose = (item: CommandItem) => {
    if (item.disabled || item.loading) {
      return;
    }
    item.onSelect?.();
    onSelect?.(item);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.nativeEvent.isComposing) {
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = nextEnabled(
        rows,
        activeIndex,
        event.key === "ArrowDown" ? 1 : -1,
      );
      if (next >= 0) {
        setActiveId(rows[next].id);
      }
    } else if (event.key === "Enter" && active) {
      event.preventDefault();
      choose(active);
    }
  };

  const status = loading ? "Loading…" : rows.length === 0 ? emptyText : null;

  return (
    <div
      data-slot="command"
      className={cn("ui:flex ui:min-h-0 ui:flex-col", className)}
    >
      <div className="ui:flex ui:items-center ui:gap-2 ui:border-b ui:border-border ui:px-3">
        <SearchIcon
          aria-hidden
          className="ui:size-4 ui:shrink-0 ui:text-muted-foreground"
        />
        <input
          data-slot="command-input"
          role="combobox"
          aria-label={label}
          aria-expanded
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active ? optionId(active) : undefined}
          // biome-ignore lint/a11y/noAutofocus: a menu or palette opened to search should take the typing at once.
          autoFocus={autoFocus}
          autoComplete="off"
          spellCheck={false}
          placeholder={placeholder}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          className="ui:h-10 ui:min-w-0 ui:flex-1 ui:border-0 ui:bg-transparent ui:font-sans ui:text-body-small ui:text-foreground ui:outline-none ui:placeholder:text-muted-foreground"
        />
      </div>
      <div
        role="listbox"
        id={listId}
        aria-label={label}
        // An empty listbox fails the accessibility scan; the status row speaks instead.
        hidden={status !== null}
        className={cn(
          "ui:min-h-0 ui:flex-1 ui:overflow-y-auto ui:p-1.5",
          listClassName,
        )}
      >
        {status === null &&
          visible.map((group, index) => (
            <CommandGroupView
              key={group.id}
              group={group}
              separated={index > 0}
              headingId={`${id}-group-${group.id}`}
              activeId={active?.id}
              optionId={optionId}
              onActivate={(item) => setActiveId(item.id)}
              onChoose={choose}
            />
          ))}
      </div>
      {status && (
        <output className="ui:block ui:px-3 ui:py-6 ui:text-center ui:font-sans ui:text-body-small ui:text-muted-foreground">
          {status}
        </output>
      )}
      {footer && (
        <div
          data-slot="command-footer"
          className="ui:flex ui:items-center ui:gap-4 ui:border-t ui:border-border ui:px-3 ui:py-2 ui:font-sans ui:text-caption ui:text-muted-foreground"
        >
          {footer}
        </div>
      )}
    </div>
  );
}

type GroupViewProps = Readonly<{
  group: CommandGroup;
  separated: boolean;
  headingId: string;
  activeId: string | undefined;
  optionId: (item: CommandItem) => string;
  onActivate: (item: CommandItem) => void;
  onChoose: (item: CommandItem) => void;
}>;

function CommandGroupView({
  group,
  separated,
  headingId,
  activeId,
  optionId,
  onActivate,
  onChoose,
}: GroupViewProps): JSX.Element {
  const hasChecks = group.items.some((item) => item.checked !== undefined);
  return (
    <>
      {separated && <div aria-hidden className={MENU_SEPARATOR} />}
      {/* biome-ignore lint/a11y/useSemanticElements: a listbox may hold only options and groups; a fieldset is neither. */}
      <div role="group" aria-labelledby={group.heading ? headingId : undefined}>
        {group.heading && (
          <div id={headingId} className={MENU_LABEL}>
            {group.heading}
          </div>
        )}
        {group.items.map((item) => {
          const unavailable = item.disabled || item.loading;
          return (
            // biome-ignore lint/a11y/useFocusableInteractive: focus stays on the combobox input, which points here with aria-activedescendant.
            // biome-ignore lint/a11y/useKeyWithClickEvents: the combobox input handles the keyboard for every row.
            <div
              key={item.id}
              id={optionId(item)}
              role="option"
              aria-selected={item.id === activeId}
              aria-checked={item.checked}
              aria-disabled={unavailable || undefined}
              aria-busy={item.loading || undefined}
              {...describedRowProps(optionId(item), item.description)}
              data-highlighted={item.id === activeId ? "" : undefined}
              data-disabled={unavailable ? "" : undefined}
              data-destructive={item.destructive || undefined}
              className={menuItemClass(item)}
              onMouseDown={(event) => event.preventDefault()}
              onMouseMove={() => {
                if (!unavailable && item.id !== activeId) {
                  onActivate(item);
                }
              }}
              onClick={() => onChoose(item)}
            >
              <MenuItemBody
                icon={item.icon}
                shortcut={item.shortcut}
                description={item.description}
                destructive={item.destructive}
                loading={item.loading}
                rowId={optionId(item)}
                indicator={
                  hasChecks ? (
                    <div className={MENU_INDICATOR_SLOT}>
                      {item.checked && <MenuCheck />}
                    </div>
                  ) : undefined
                }
              >
                {item.label}
              </MenuItemBody>
            </div>
          );
        })}
      </div>
    </>
  );
}
