import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { getPortalContainer } from "@v1/lib/portal";
import { Popover as PopoverPrimitive } from "radix-ui";
import {
  type FocusEvent,
  type JSX,
  type KeyboardEvent,
  useId,
  useRef,
  useState,
} from "react";
import { Chip } from "./Chip";
import { Listbox } from "./Listbox";
import type { SelectOption } from "./options";
import { ICON_BUTTON, isInside, listContentProps } from "./shared";
import { LIST_SURFACE, TRIGGER_CHEVRON, TRIGGER_FRAME } from "./trigger";
import { type LoadOptions, useAsyncOptions } from "./useAsyncOptions";
import { useListbox } from "./useListbox";

const ChevronIcon = ACTION_ICONS.expand;
const NO_OPTIONS: readonly SelectOption[] = [];
const NO_VALUES: readonly string[] = [];

export type MultiSelectProps = Readonly<{
  options?: readonly SelectOption[];
  /** Server-loaded options; when given, `options` are ignored and the query is sent to the loader. */
  loadOptions?: LoadOptions;
  value?: readonly string[];
  defaultValue?: readonly string[];
  onValueChange?: (values: readonly string[]) => void;
  /** The options for values not in `options` yet, e.g. saved choices before the first load. */
  selectedOptions?: readonly SelectOption[];
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

/**
 * Several choices from a long or server-loaded list, shown as chips before
 * the input. Typing filters (or, with `loadOptions`, queries the server);
 * Enter or a click toggles an option and keeps the list open with the query
 * cleared; Backspace in an empty input removes the last chip.
 */
export function MultiSelect({
  options = NO_OPTIONS,
  loadOptions,
  value: valueProp,
  defaultValue = NO_VALUES,
  onValueChange,
  selectedOptions,
  placeholder,
  emptyText,
  disabled,
  invalid,
  id,
  name,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
  "aria-describedby": ariaDescribedBy,
  className,
}: MultiSelectProps): JSX.Element {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const value = valueProp ?? uncontrolled;
  // The last loaded options, fed back to the engine (it filters nothing then).
  const [served, setServed] = useState(NO_OPTIONS);
  const known = loadOptions ? served : options;

  const frameRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const listbox = useListbox({
    options: known,
    selected: value,
    onSelect: toggle,
    filter: !loadOptions,
    id: useId(),
  });
  const loaded = useAsyncOptions(loadOptions, listbox.query, listbox.open);
  if (loadOptions && loaded.options !== served) {
    setServed(loaded.options);
  }

  // Every option seen, by value, so a chip keeps its label when the list (or
  // a server response) no longer holds its option. Filling is idempotent, so
  // it runs while rendering, once per new list.
  const seen = useRef(new Map<string, SelectOption>());
  const seenList = useRef<readonly SelectOption[] | null>(null);
  if (seenList.current !== known) {
    seenList.current = known;
    for (const option of known) {
      seen.current.set(option.value, option);
    }
  }
  const labelOf = (item: string) =>
    seen.current.get(item)?.label ??
    selectedOptions?.find((option) => option.value === item)?.label ??
    item;

  function change(next: readonly string[]) {
    setUncontrolled(next);
    onValueChange?.(next);
  }

  function remove(item: string) {
    change(value.filter((other) => other !== item));
  }

  /** Adds or removes the option; the list stays open for the next one. */
  function toggle(option: SelectOption) {
    change(
      value.includes(option.value)
        ? value.filter((other) => other !== option.value)
        : [...value, option.value],
    );
    listbox.setQuery("");
  }

  /** Closes the list and drops the typed text. */
  function close() {
    listbox.setOpen(false);
    listbox.setQuery("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // With no text to delete, Backspace takes the last chip instead.
    if (event.key === "Backspace" && listbox.query === "" && value.length > 0) {
      event.preventDefault();
      remove(value[value.length - 1]);
      return;
    }
    listbox.onKeyDown(event);
    if (event.key === "Escape" || event.key === "Tab") {
      close();
    }
  }

  /** Focus leaving the field and its list closes the list. */
  function onBlur(event: FocusEvent<HTMLElement>) {
    if (!isInside(frameRef.current, contentRef.current, event.relatedTarget)) {
      close();
    }
  }

  return (
    <PopoverPrimitive.Root
      open={listbox.open}
      onOpenChange={(next) => listbox.setOpen(next)}
    >
      <PopoverPrimitive.Anchor asChild>
        <div
          ref={frameRef}
          data-slot="multi-select"
          data-state={listbox.open ? "open" : "closed"}
          data-invalid={invalid ? "" : undefined}
          data-disabled={disabled ? "" : undefined}
          className={cn(
            TRIGGER_FRAME,
            "ui:h-auto ui:min-h-8 ui:flex-wrap ui:gap-1 ui:py-1",
            "ui:has-[[data-slot=control]:focus-visible]:focus-ring",
            className,
          )}
        >
          {value.map((item) => (
            <Chip
              key={item}
              label={labelOf(item)}
              disabled={disabled}
              onRemove={() => {
                remove(item);
                inputRef.current?.focus();
              }}
            />
          ))}
          <input
            ref={inputRef}
            data-slot="control"
            {...listbox.comboboxProps}
            id={id}
            aria-label={ariaLabel}
            aria-labelledby={ariaLabelledBy}
            aria-describedby={ariaDescribedBy}
            aria-invalid={invalid || undefined}
            disabled={disabled}
            placeholder={value.length === 0 ? placeholder : undefined}
            autoComplete="off"
            spellCheck={false}
            value={listbox.query}
            onChange={(event) => listbox.setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            onBlur={onBlur}
            className="ui:min-w-16 ui:flex-1 ui:border-0 ui:bg-transparent ui:p-0 ui:text-body ui:text-foreground ui:outline-none ui:placeholder:text-muted-foreground"
          />
          <button
            type="button"
            tabIndex={-1}
            aria-label="Show options"
            aria-expanded={listbox.open}
            disabled={disabled}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              // setOpen(true) re-lands the active row, so it runs only when closed.
              if (listbox.open) {
                close();
              } else {
                listbox.setOpen(true);
              }
              inputRef.current?.focus();
            }}
            className={cn(ICON_BUTTON, "ui:-mr-1 ui:size-6")}
          >
            <ChevronIcon aria-hidden className={TRIGGER_CHEVRON} />
          </button>
          {/* A disabled control does not submit, so neither do these. */}
          {name && !disabled
            ? value.map((item) => (
                <input key={item} type="hidden" name={name} value={item} />
              ))
            : null}
        </div>
      </PopoverPrimitive.Anchor>
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
            loading={loaded.loading}
            error={Boolean(loaded.error)}
            emptyText={emptyText}
            multiselectable
          />
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
