import {
  type KeyboardEvent,
  useCallback,
  useMemo,
  useRef,
  useState,
} from "react";
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
  /** The stable id of the option with `value`, the same at every index. */
  optionIdFor: (value: string) => string;
  /** The id of `visible[index]`. */
  optionId: (index: number) => string;
  /** The caller's `selected`, passed through for the rows' `aria-selected`. */
  selected: readonly string[];
  /** The caller's `onSelect`, passed through for a row click. */
  onSelect: (option: SelectOption) => void;
  /**
   * Attach to the input: ArrowDown/Up (opens when closed), Home, End, Enter
   * (default-prevented whenever open), Escape, Tab.
   */
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
 * option is gone. Each option's id is tied to its value (an ordinal given the
 * first time the value is seen, never reused while mounted), so when the
 * first match changes `aria-activedescendant` changes too and a screen reader
 * announces the new option.
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

  // Ordinals by value, numbered in list order; filling is idempotent, so it
  // runs while rendering, once per new list.
  const ordinals = useRef(new Map<string, number>());
  const ordinalsList = useRef<readonly SelectOption[] | null>(null);
  if (ordinalsList.current !== options) {
    ordinalsList.current = options;
    for (const option of options) {
      if (!ordinals.current.has(option.value)) {
        ordinals.current.set(option.value, ordinals.current.size);
      }
    }
  }

  const listId = `${id}-listbox`;
  const optionIdFor = useCallback(
    (value: string) => {
      let ordinal = ordinals.current.get(value);
      if (ordinal === undefined) {
        ordinal = ordinals.current.size;
        ordinals.current.set(value, ordinal);
      }
      return `${id}-option-${ordinal}`;
    },
    [id],
  );
  const optionId = useCallback(
    (index: number) => optionIdFor(visible[index].value),
    [optionIdFor, visible],
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
        if (!open) {
          return;
        }
        // While open, Enter never submits the form, even with nothing active.
        event.preventDefault();
        const option = visible[activeIndex];
        if (option && !option.disabled) {
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
    optionIdFor,
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
