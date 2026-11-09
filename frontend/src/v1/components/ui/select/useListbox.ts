import { type KeyboardEvent, useCallback, useMemo, useState } from "react";
import { matchesQuery, type SelectOption } from "./options";

export type UseListboxOptions = Readonly<{
  options: readonly SelectOption[];
  /** Values currently selected (one for Combobox, many for MultiSelect). */
  selected: readonly string[];
  onSelect: (option: SelectOption) => void;
  /** When false, the query does not filter (server-side filtering). Default true. */
  filter?: boolean;
  id: string;
}>;

export type Listbox = Readonly<{
  open: boolean;
  setOpen: (open: boolean) => void;
  query: string;
  setQuery: (query: string) => void;
  visible: readonly SelectOption[];
  activeIndex: number;
  setActiveIndex: (i: number) => void;
  activeId: string | undefined;
  listId: string;
  optionId: (index: number) => string;
  /** The caller's `selected`, passed through for the rows' `aria-selected`. */
  selected: readonly string[];
  /** The caller's `onSelect`, passed through for a row click. */
  onSelect: (option: SelectOption) => void;
  /** Attach to the input: ArrowDown/Up (opens when closed), Home, End, Enter, Escape, Tab. */
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  /** Attach to the input's aria-* props. */
  comboboxProps: {
    role: "combobox";
    "aria-expanded": boolean;
    "aria-controls": string;
    "aria-autocomplete": "list";
    "aria-activedescendant": string | undefined;
  };
}>;

const firstEnabled = (list: readonly SelectOption[]): number =>
  list.findIndex((option) => !option.disabled);

function lastEnabled(list: readonly SelectOption[]): number {
  for (let index = list.length - 1; index >= 0; index--) {
    if (!list[index].disabled) {
      return index;
    }
  }
  return -1;
}

/** The next enabled index from `from` in `step` direction; `from` when none (no wrap). */
function nextEnabled(
  list: readonly SelectOption[],
  from: number,
  step: 1 | -1,
): number {
  for (
    let index = from + step;
    index >= 0 && index < list.length;
    index += step
  ) {
    if (!list[index].disabled) {
      return index;
    }
  }
  return from;
}

/**
 * The state and keyboard of a combobox's listbox: the query, the filtered
 * (`visible`) options and the active option, which focus never moves to (the
 * input points at it with `aria-activedescendant`).
 *
 * The active option is tracked by value, so when `visible` changes it follows
 * its option to the new index, and moves to the first enabled option when its
 * option is gone.
 */
export function useListbox({
  options,
  selected,
  onSelect,
  filter = true,
  id,
}: UseListboxOptions): Listbox {
  const [open, setOpenState] = useState(false);
  const [query, setQueryState] = useState("");
  const [activeValue, setActiveValue] = useState<string | null>(null);

  const filterBy = useCallback(
    (text: string) =>
      filter ? options.filter((option) => matchesQuery(option, text)) : options,
    [filter, options],
  );
  const visible = useMemo(() => filterBy(query), [filterBy, query]);

  const tracked = visible.findIndex((option) => option.value === activeValue);
  const activeIndex = tracked === -1 ? firstEnabled(visible) : tracked;

  const setActiveIndex = (index: number) =>
    setActiveValue(visible[index]?.value ?? null);

  const setQuery = (next: string) => {
    setQueryState(next);
    if (next !== "") {
      setOpenState(true);
    }
    const list = filterBy(next);
    setActiveValue(list[firstEnabled(list)]?.value ?? null);
  };

  const listId = `${id}-listbox`;
  const optionId = useCallback(
    (index: number) => `${id}-option-${index}`,
    [id],
  );
  const activeId = open && activeIndex >= 0 ? optionId(activeIndex) : undefined;

  const openList = () => {
    const chosen = visible.findIndex(
      (option) => !option.disabled && selected.includes(option.value),
    );
    setActiveIndex(chosen === -1 ? firstEnabled(visible) : chosen);
    setOpenState(true);
  };

  /** Opening lands where the arrows do: the selection, else the first enabled option. */
  const setOpen = (next: boolean) => (next ? openList() : setOpenState(false));

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    switch (event.key) {
      case "ArrowDown":
      case "ArrowUp":
        event.preventDefault();
        if (!open) {
          openList();
        } else if (activeIndex >= 0) {
          setActiveIndex(
            nextEnabled(
              visible,
              activeIndex,
              event.key === "ArrowDown" ? 1 : -1,
            ),
          );
        }
        return;
      case "Home":
      case "End":
        if (open) {
          event.preventDefault();
          setActiveIndex(
            event.key === "Home" ? firstEnabled(visible) : lastEnabled(visible),
          );
        }
        return;
      case "Enter": {
        // Enter that commits an IME composition is not a selection.
        if (event.nativeEvent.isComposing) {
          return;
        }
        const option = visible[activeIndex];
        if (open && option && !option.disabled) {
          event.preventDefault();
          onSelect(option);
        }
        return;
      }
      case "Escape":
        if (open) {
          event.preventDefault();
          setOpenState(false);
        }
        return;
      case "Tab":
        setOpenState(false);
        return;
      default:
    }
  };

  return {
    open,
    setOpen,
    query,
    setQuery,
    visible,
    activeIndex,
    setActiveIndex,
    activeId,
    listId,
    optionId,
    selected,
    onSelect,
    onKeyDown,
    comboboxProps: {
      role: "combobox",
      "aria-expanded": open,
      "aria-controls": listId,
      "aria-autocomplete": "list",
      "aria-activedescendant": activeId,
    },
  };
}
