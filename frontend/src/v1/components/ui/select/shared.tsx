import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { getPortalContainer } from "@v1/lib/portal";
import { Popover as PopoverPrimitive } from "radix-ui";
import {
  type FocusEvent,
  type JSX,
  type RefObject,
  useId,
  useRef,
  useState,
} from "react";
import { Listbox } from "./Listbox";
import type { SelectOption } from "./options";
import { LIST_SURFACE, TRIGGER_CHEVRON } from "./trigger";
import { type LoadOptions, useAsyncOptions } from "./useAsyncOptions";
import { type Listbox as ListboxState, useListbox } from "./useListbox";

/*
 * Pieces shared by the popover-list fields (Combobox, MultiSelect), whose
 * focus stays in an input inside the frame while the list is open.
 */

const ChevronIcon = ACTION_ICONS.expand;
const NO_OPTIONS: readonly SelectOption[] = [];

/** The props every popover-list field takes besides its value. */
export type ListFieldProps = Readonly<{
  options?: readonly SelectOption[];
  /** Server-loaded options; when given, `options` are ignored and the query is sent to the loader. */
  loadOptions?: LoadOptions;
  placeholder?: string;
  emptyText?: string;
  disabled?: boolean;
  invalid?: boolean;
  id?: string;
  name?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
  /** Classes for the frame. */
  className?: string;
}>;

/** The field props that land on the input (`useFieldControl`'s seam). */
export function fieldInputProps(field: ListFieldProps) {
  return {
    id: field.id,
    "aria-label": field["aria-label"],
    "aria-labelledby": field["aria-labelledby"],
    "aria-describedby": field["aria-describedby"],
    "aria-invalid": field.invalid || undefined,
    disabled: field.disabled,
  } as const;
}

/** An icon button inside the frame (clear, chevron). */
export const ICON_BUTTON =
  "ui:flex ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-md ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:hover:text-foreground ui:focus-visible:focus-ring ui:disabled:pointer-events-none";

/** Whether `target` (a blur's `relatedTarget`) is inside the frame or the list. */
export function isInside(
  frame: HTMLElement | null,
  content: HTMLElement | null,
  target: EventTarget | null,
): boolean {
  return (
    target instanceof Node &&
    Boolean(frame?.contains(target) || content?.contains(target))
  );
}

/** A blur handler that closes the list when focus leaves the frame and the list. */
export function closeOnLeave(
  frameRef: RefObject<HTMLElement | null>,
  contentRef: RefObject<HTMLElement | null>,
  close: () => void,
) {
  return (event: FocusEvent<HTMLElement>) => {
    if (!isInside(frameRef.current, contentRef.current, event.relatedTarget)) {
      close();
    }
  };
}

/**
 * The chevron's toggle: closes through the field's `close`, or opens, which
 * re-lands the active row, so only when closed. Focus stays in the input.
 */
export function toggleList(
  listbox: ListboxState,
  close: () => void,
  input: HTMLInputElement | null,
): void {
  if (listbox.open) {
    close();
  } else {
    listbox.setOpen(true);
  }
  input?.focus();
}

/**
 * Props for the list's `Popover.Content`: no dialog role (the listbox inside
 * is the popup), focus never moves into or back from it, a press inside the
 * frame is not outside, and a press on the list's padding keeps focus in the
 * input.
 */
export function listContentProps(frameRef: RefObject<HTMLElement | null>) {
  return {
    role: "presentation",
    onOpenAutoFocus: (event: Event) => event.preventDefault(),
    onCloseAutoFocus: (event: Event) => event.preventDefault(),
    onInteractOutside: (event: Event) => {
      const target = event.target;
      if (target instanceof Node && frameRef.current?.contains(target)) {
        event.preventDefault();
      }
    },
    onMouseDown: (event: { preventDefault: () => void }) =>
      event.preventDefault(),
  } as const;
}

export type ChevronButtonProps = Readonly<{
  open: boolean;
  disabled?: boolean;
  onToggle: () => void;
  /** The listbox's id, for `aria-controls`. */
  listId: string;
}>;

/**
 * The "Show options" chevron at the end of the frame: out of the tab order,
 * and its press never takes focus from the input.
 */
export function ChevronButton({
  open,
  disabled,
  onToggle,
  listId,
}: ChevronButtonProps): JSX.Element {
  return (
    <button
      type="button"
      tabIndex={-1}
      aria-label="Show options"
      aria-expanded={open}
      aria-controls={listId}
      disabled={disabled}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onToggle}
      className={cn(ICON_BUTTON, "ui:-mr-1 ui:size-6")}
    >
      <ChevronIcon aria-hidden className={TRIGGER_CHEVRON} />
    </button>
  );
}

export type ListPopoverProps = Readonly<{
  listbox: ListboxState;
  loading: boolean;
  error: boolean;
  emptyText?: string;
  multiselectable?: boolean;
  frameRef: RefObject<HTMLElement | null>;
  contentRef: RefObject<HTMLDivElement | null>;
  /** The field's name, given to the listbox. */
  "aria-label"?: string;
  "aria-labelledby"?: string;
}>;

/**
 * The list under the frame: a portalled `Popover.Content` with the list
 * surface, the frame's width, and the `Listbox` as its one scroll element,
 * capped by the surface's height and by the height Radix finds free around
 * the frame, so a short viewport never leaves the active option off-screen.
 * The caller's `Popover.Root` holds the open state (`listbox.open`).
 */
export function ListPopover({
  listbox,
  loading,
  error,
  emptyText,
  multiselectable,
  frameRef,
  contentRef,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
}: ListPopoverProps): JSX.Element {
  return (
    <PopoverPrimitive.Portal container={getPortalContainer()}>
      <PopoverPrimitive.Content
        ref={contentRef}
        {...listContentProps(frameRef)}
        sideOffset={4}
        align="start"
        className={cn(
          LIST_SURFACE,
          "ui:flex ui:flex-col ui:overflow-hidden ui:w-(--radix-popover-trigger-width)",
        )}
      >
        <Listbox
          listbox={listbox}
          loading={loading}
          error={error}
          emptyText={emptyText}
          multiselectable={multiselectable}
          aria-label={ariaLabel}
          aria-labelledby={ariaLabelledBy}
          className="ui:max-h-(--radix-popover-content-available-height)"
        />
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  );
}

export type UseLoadedOptions = Readonly<{
  loadOptions: LoadOptions | undefined;
  /** The client-side options, used when there is no `loadOptions`. */
  staticOptions: readonly SelectOption[];
  /** Preset options for values not loaded yet (`selectedOption(s)`). */
  extraSelected: readonly SelectOption[] | undefined;
  /** Passed to `useListbox`. */
  selected: readonly string[];
  onSelect: (option: SelectOption) => void;
}>;

export type LoadedOptions = Readonly<{
  listbox: ListboxState;
  /** The options the list holds now: the static ones, or the last loaded. */
  known: readonly SelectOption[];
  loading: boolean;
  error: boolean;
  /** The option for `value`: from `known`, else any option seen, else a preset one. */
  lookup: (value: string) => SelectOption | undefined;
}>;

/**
 * A popover-list field's options and its `useListbox`: the static options,
 * or, with `loadOptions`, the ones loaded for the current query while the
 * list is open. It creates the listbox itself, because the listbox's query
 * and open state drive the loader whose result feeds the listbox back (the
 * `served` mirror, set while rendering). Every option seen is remembered by
 * value, so a selected label survives a list (or a server response) that no
 * longer holds it.
 */
export function useLoadedOptions({
  loadOptions,
  staticOptions,
  extraSelected,
  selected,
  onSelect,
}: UseLoadedOptions): LoadedOptions {
  // The last loaded options, fed back to the listbox (it filters nothing then).
  const [served, setServed] = useState(NO_OPTIONS);
  const known = loadOptions ? served : staticOptions;
  const listbox = useListbox({
    options: known,
    selected,
    onSelect,
    filter: !loadOptions,
    id: useId(),
  });
  const loaded = useAsyncOptions(loadOptions, listbox.query, listbox.open);
  if (loadOptions && loaded.options !== served) {
    setServed(loaded.options);
  }

  // Filling is idempotent, so it runs while rendering, once per new list.
  const seen = useRef(new Map<string, SelectOption>());
  const seenList = useRef<readonly SelectOption[] | null>(null);
  if (seenList.current !== known) {
    seenList.current = known;
    for (const option of known) {
      seen.current.set(option.value, option);
    }
  }

  const lookup = (value: string) =>
    known.find((option) => option.value === value) ??
    seen.current.get(value) ??
    extraSelected?.find((option) => option.value === value);

  return {
    listbox,
    known,
    loading: loaded.loading,
    error: loaded.error !== null,
    lookup,
  };
}
