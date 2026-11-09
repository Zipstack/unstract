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
import { Listbox } from "./Listbox";
import { OPTION_LEADING_CLASS } from "./OptionRow";
import type { SelectOption } from "./options";
import { ICON_BUTTON, isInside, listContentProps } from "./shared";
import { LIST_SURFACE, TRIGGER_CHEVRON, TRIGGER_FRAME } from "./trigger";
import { type LoadOptions, useAsyncOptions } from "./useAsyncOptions";
import { useListbox } from "./useListbox";

const ChevronIcon = ACTION_ICONS.expand;
const ClearIcon = ACTION_ICONS.close;
const NO_OPTIONS: readonly SelectOption[] = [];

export type ComboboxProps = Readonly<{
  options?: readonly SelectOption[];
  /** Server-loaded options; when given, `options` are ignored and the query is sent to the loader. */
  loadOptions?: LoadOptions;
  value?: string | null;
  defaultValue?: string | null;
  onValueChange?: (value: string | null, option: SelectOption | null) => void;
  /** The option for `value` when it is not in `options` yet, e.g. a saved choice before the first load. */
  selectedOption?: SelectOption | null;
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
 * A single choice from a long or server-loaded list: typing filters (or, with
 * `loadOptions`, queries the server) and opens the list; focus stays on the
 * input, which points at the active option with `aria-activedescendant`.
 * While the list is closed the input shows the selected label; Escape and
 * leaving the field drop the typed text and show it again.
 */
export function Combobox({
  options = NO_OPTIONS,
  loadOptions,
  value: valueProp,
  defaultValue = null,
  onValueChange,
  selectedOption,
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
}: ComboboxProps): JSX.Element {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const value = valueProp === undefined ? uncontrolled : valueProp;
  // Typing since the list last closed: the input shows the query, not the label.
  const [editing, setEditing] = useState(false);
  // The last loaded options, fed back to the engine (it filters nothing then).
  const [served, setServed] = useState(NO_OPTIONS);
  const known = loadOptions ? served : options;

  const frameRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const listbox = useListbox({
    options: known,
    selected: value === null ? [] : [value],
    onSelect: select,
    filter: !loadOptions,
    id: useId(),
  });
  const loaded = useAsyncOptions(loadOptions, listbox.query, listbox.open);
  if (loadOptions && loaded.options !== served) {
    setServed(loaded.options);
  }

  // Every option seen, by value, so the selected label survives a list (or a
  // server response) that no longer holds it. Filling is idempotent, so it
  // runs while rendering, once per new list.
  const seen = useRef(new Map<string, SelectOption>());
  const seenList = useRef<readonly SelectOption[] | null>(null);
  if (seenList.current !== known) {
    seenList.current = known;
    for (const option of known) {
      seen.current.set(option.value, option);
    }
  }
  if (selectedOption) {
    seen.current.set(selectedOption.value, selectedOption);
  }
  const selected =
    value === null
      ? undefined
      : (known.find((option) => option.value === value) ??
        seen.current.get(value));

  /** Closes the list and drops the typed text, so the label shows again. */
  function close() {
    listbox.setOpen(false);
    listbox.setQuery("");
    setEditing(false);
  }

  function select(option: SelectOption) {
    setUncontrolled(option.value);
    seen.current.set(option.value, option);
    onValueChange?.(option.value, option);
    close();
  }

  function clear() {
    setUncontrolled(null);
    onValueChange?.(null, null);
    close();
    inputRef.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    listbox.onKeyDown(event);
    // Tab may move to the clear button, still inside the field.
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
      // Escape and leaving the field restore the text themselves.
      onOpenChange={(next) => listbox.setOpen(next)}
    >
      <PopoverPrimitive.Anchor asChild>
        <div
          ref={frameRef}
          data-slot="combobox"
          data-state={listbox.open ? "open" : "closed"}
          data-invalid={invalid ? "" : undefined}
          data-disabled={disabled ? "" : undefined}
          className={cn(
            TRIGGER_FRAME,
            "ui:has-[[data-slot=control]:focus-visible]:focus-ring",
            className,
          )}
        >
          {selected?.leading && !editing ? (
            <span data-slot="option-leading" className={OPTION_LEADING_CLASS}>
              {selected.leading}
            </span>
          ) : null}
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
            placeholder={placeholder}
            autoComplete="off"
            spellCheck={false}
            value={editing ? listbox.query : (selected?.label ?? "")}
            onChange={(event) => {
              setEditing(true);
              listbox.setQuery(event.target.value);
            }}
            onKeyDown={onKeyDown}
            onBlur={onBlur}
            className="ui:min-w-0 ui:flex-1 ui:border-0 ui:bg-transparent ui:p-0 ui:text-body ui:text-foreground ui:outline-none ui:placeholder:text-muted-foreground"
          />
          {value !== null && !disabled ? (
            <button
              type="button"
              aria-label="Clear"
              onClick={clear}
              onBlur={onBlur}
              className={cn(ICON_BUTTON, "ui:size-4")}
            >
              <ClearIcon aria-hidden className="ui:size-3.5" />
            </button>
          ) : null}
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
          {/* A disabled control does not submit, so neither does this. */}
          {name && !disabled ? (
            <input type="hidden" name={name} value={value ?? ""} />
          ) : null}
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
          />
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
