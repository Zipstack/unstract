import { cn } from "@v1/lib/cn";
import { Popover as PopoverPrimitive } from "radix-ui";
import {
  type JSX,
  type KeyboardEvent,
  type MouseEvent,
  useMemo,
  useRef,
  useState,
} from "react";
import { Chip } from "./Chip";
import type { SelectOption } from "./options";
import {
  ChevronButton,
  closeOnLeave,
  fieldInputProps,
  type ListFieldProps,
  ListPopover,
  toggleList,
  useLoadedOptions,
} from "./shared";
import { TRIGGER_FRAME } from "./trigger";

const NO_OPTIONS: readonly SelectOption[] = [];
const NO_VALUES: readonly string[] = [];

export type MultiSelectProps = ListFieldProps &
  Readonly<{
    /** The selected values, in chip order; duplicates are collapsed. */
    value?: readonly string[];
    defaultValue?: readonly string[];
    onValueChange?: (values: readonly string[]) => void;
    /** The options for values not in `options` yet, e.g. saved choices before the first load. */
    selectedOptions?: readonly SelectOption[];
  }>;

/**
 * Several choices from a long or server-loaded list, shown as chips before
 * the input. A click on the input or the frame opens the list; focus alone
 * does not. Typing filters (or, with `loadOptions`, queries the server);
 * Enter or a click toggles an option and keeps the list open with the query
 * cleared; Backspace in an empty input removes the last chip.
 */
export function MultiSelect(props: MultiSelectProps): JSX.Element {
  const {
    options = NO_OPTIONS,
    loadOptions,
    value: valueProp,
    defaultValue = NO_VALUES,
    onValueChange,
    selectedOptions,
    disabled,
    name,
  } = props;
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const raw = valueProp ?? uncontrolled;
  const value = useMemo(() => [...new Set(raw)], [raw]);

  const frameRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // A chip keeps its label when the list (or a server response) no longer
  // holds its option: the lookup remembers every option seen.
  const { listbox, loading, error, lookup } = useLoadedOptions({
    loadOptions,
    staticOptions: options,
    extraSelected: selectedOptions,
    selected: value,
    onSelect: toggle,
  });

  function change(next: readonly string[]) {
    setUncontrolled(next);
    onValueChange?.(next);
  }

  function remove(item: string) {
    change(value.filter((other) => other !== item));
  }

  /**
   * Adds or removes the option; the list stays open for the next one, with
   * the query cleared and the toggled option still active.
   */
  function toggle(option: SelectOption) {
    change(
      value.includes(option.value)
        ? value.filter((other) => other !== option.value)
        : [...value, option.value],
    );
    const index = listbox.visible.findIndex(
      (other) => other.value === option.value,
    );
    listbox.setQuery("");
    // setQuery lands on the first option; the active row is tracked by value,
    // so this keeps the toggled option active in the unfiltered list.
    listbox.setActiveIndex(index);
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

  const onBlur = closeOnLeave(frameRef, contentRef, close);

  /**
   * A press on the frame's padding or a chip's label focuses the input and
   * opens the list, as a press on the input does; buttons keep their own.
   */
  function onFrameMouseDown(event: MouseEvent<HTMLDivElement>) {
    const target = event.target;
    if (
      disabled ||
      target === inputRef.current ||
      (target instanceof Element && target.closest("button"))
    ) {
      return;
    }
    event.preventDefault();
    inputRef.current?.focus();
    if (!listbox.open) {
      listbox.setOpen(true);
    }
  }

  return (
    <PopoverPrimitive.Root
      open={listbox.open}
      onOpenChange={(next) => (next ? listbox.setOpen(true) : close())}
    >
      <PopoverPrimitive.Anchor asChild>
        {/* biome-ignore lint/a11y/noStaticElementInteractions: the mousedown only forwards a press on the padding to the input, which the keyboard reaches directly. */}
        {/* biome-ignore lint/a11y/noNoninteractiveElementInteractions: as above; the frame is not a control of its own. */}
        <div
          ref={frameRef}
          data-slot="multi-select"
          data-state={listbox.open ? "open" : "closed"}
          data-invalid={props.invalid ? "" : undefined}
          data-disabled={disabled ? "" : undefined}
          onMouseDown={onFrameMouseDown}
          className={cn(
            TRIGGER_FRAME,
            "ui:h-auto ui:min-h-8 ui:flex-wrap ui:gap-1 ui:py-1",
            "ui:has-[[data-slot=control]:focus-visible]:focus-ring",
            props.className,
          )}
        >
          {value.map((item) => (
            <Chip
              key={item}
              label={lookup(item)?.label ?? item}
              disabled={disabled}
              // Backspace removes chips from the input; one tab stop, not N.
              removeFocusable={false}
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
            {...fieldInputProps(props)}
            placeholder={value.length === 0 ? props.placeholder : undefined}
            autoComplete="off"
            spellCheck={false}
            value={listbox.query}
            onChange={(event) => listbox.setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            onClick={() => {
              if (!listbox.open) {
                listbox.setOpen(true);
              }
            }}
            onBlur={onBlur}
            className="ui:min-w-16 ui:flex-1 ui:border-0 ui:bg-transparent ui:p-0 ui:text-body ui:text-foreground ui:outline-none ui:placeholder:text-muted-foreground"
          />
          <ChevronButton
            open={listbox.open}
            disabled={disabled}
            listId={listbox.listId}
            onToggle={() => toggleList(listbox, close, inputRef.current)}
          />
          {/* A disabled control does not submit, so neither do these. */}
          {name && !disabled
            ? value.map((item) => (
                <input key={item} type="hidden" name={name} value={item} />
              ))
            : null}
        </div>
      </PopoverPrimitive.Anchor>
      <ListPopover
        listbox={listbox}
        loading={loading}
        error={error}
        emptyText={props.emptyText}
        multiselectable
        frameRef={frameRef}
        contentRef={contentRef}
        aria-label={props["aria-label"]}
        aria-labelledby={props["aria-labelledby"]}
      />
    </PopoverPrimitive.Root>
  );
}
