import { fieldControlClass, fieldFrameVariants } from "@v1/components/ui/form";
import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { mergeRefs } from "@v1/lib/merge-refs";
import { Popover as PopoverPrimitive } from "radix-ui";
import {
  type JSX,
  type KeyboardEvent,
  type Ref,
  useMemo,
  useRef,
  useState,
} from "react";
import { OPTION_LEADING_CLASS } from "./OptionRow";
import type { SelectOption } from "./options";
import {
  ChevronButton,
  closeOnLeave,
  fieldInputProps,
  ICON_BUTTON,
  type ListFieldProps,
  ListPopover,
  listName,
  toggleList,
  useListFieldControl,
  useLoadedOptions,
} from "./shared";
import { isComposing } from "./useListbox";

const ClearIcon = ACTION_ICONS.close;
const NO_OPTIONS: readonly SelectOption[] = [];

export type ComboboxProps = ListFieldProps &
  Readonly<{
    value?: string | null;
    defaultValue?: string | null;
    onValueChange?: (value: string | null, option: SelectOption | null) => void;
    /** The option for `value` when it is not in `options` yet, e.g. a saved choice before the first load. */
    selectedOption?: SelectOption | null;
    /** The text input, the focusable element. */
    ref?: Ref<HTMLInputElement>;
  }>;

/**
 * A single choice from a long or server-loaded list: typing filters (or, with
 * `loadOptions`, queries the server) and opens the list; focus stays on the
 * input, which points at the active option with `aria-activedescendant`.
 * A click on the input opens the list; focus alone does not. While the list
 * is closed the input shows the selected label, selected on focus and on
 * click so typing replaces it; Escape and leaving the field drop the typed
 * text and show it again.
 */
export function Combobox(props: ComboboxProps): JSX.Element {
  const {
    options = NO_OPTIONS,
    loadOptions,
    value: valueProp,
    defaultValue = null,
    onValueChange,
    selectedOption,
    placeholder,
    name,
    className,
    ref,
  } = props;
  const control = useListFieldControl(props);
  const { disabled } = control;
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const value = valueProp === undefined ? uncontrolled : valueProp;
  // Typing since the list last closed: the input shows the query, not the label.
  const [editing, setEditing] = useState(false);

  const frameRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const composedRef = useMemo(() => mergeRefs(inputRef, ref), [ref]);
  const contentRef = useRef<HTMLDivElement>(null);

  const { listbox, loading, error, lookup } = useLoadedOptions({
    loadOptions,
    staticOptions: options,
    extraSelected: selectedOption ? [selectedOption] : undefined,
    selected: value === null ? [] : [value],
    onSelect: select,
    disabled,
  });
  // Disabled mid-edit, the list closes (in useListbox) and the label returns.
  if (disabled && editing) {
    setEditing(false);
  }
  const selected = value === null ? undefined : lookup(value);

  /** Closes the list and drops the typed text, so the label shows again. */
  function close() {
    listbox.setOpen(false);
    listbox.setQuery("");
    setEditing(false);
  }

  function select(option: SelectOption) {
    setUncontrolled(option.value);
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
    // Tab may move to the clear button, still inside the field. An Escape
    // that cancels an IME composition is the IME's.
    if (
      event.key === "Tab" ||
      (event.key === "Escape" && !isComposing(event))
    ) {
      close();
    }
  }

  const onBlur = closeOnLeave(frameRef, contentRef, close);

  /** The shown label is selected, so the first keystroke replaces it. */
  function selectLabel(event: { currentTarget: HTMLInputElement }) {
    if (!editing) {
      event.currentTarget.select();
    }
  }

  return (
    <PopoverPrimitive.Root
      open={listbox.open}
      onOpenChange={(next) => (next ? listbox.setOpen(true) : close())}
    >
      <PopoverPrimitive.Anchor asChild>
        <div
          ref={frameRef}
          data-slot="combobox"
          data-state={listbox.open ? "open" : "closed"}
          data-invalid={control.invalid ? "" : undefined}
          data-disabled={disabled ? "" : undefined}
          className={cn(fieldFrameVariants({ focus: "within" }), className)}
        >
          {selected?.leading && !editing ? (
            <span data-slot="option-leading" className={OPTION_LEADING_CLASS}>
              {selected.leading}
            </span>
          ) : null}
          <input
            ref={composedRef}
            data-slot="control"
            {...listbox.comboboxProps}
            {...fieldInputProps(props, control)}
            placeholder={placeholder}
            autoComplete="off"
            spellCheck={false}
            value={editing ? listbox.query : (selected?.label ?? "")}
            onChange={(event) => {
              setEditing(true);
              listbox.setQuery(event.target.value);
            }}
            onKeyDown={onKeyDown}
            onFocus={selectLabel}
            onClick={(event) => {
              selectLabel(event);
              if (!listbox.open) {
                listbox.setOpen(true);
              }
            }}
            onBlur={onBlur}
            className={fieldControlClass}
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
          <ChevronButton
            open={listbox.open}
            disabled={disabled}
            listId={listbox.listId}
            onToggle={() => toggleList(listbox, close, inputRef.current)}
          />
          {/* A disabled control does not submit, so neither does this. */}
          {name && !disabled ? (
            <input type="hidden" name={name} value={value ?? ""} />
          ) : null}
        </div>
      </PopoverPrimitive.Anchor>
      <ListPopover
        listbox={listbox}
        loading={loading}
        error={error}
        emptyText={props.emptyText}
        frameRef={frameRef}
        contentRef={contentRef}
        {...listName(props, control)}
      />
    </PopoverPrimitive.Root>
  );
}
