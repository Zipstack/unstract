import { cn } from "@v1/lib/cn";
import { composeRefs } from "@v1/lib/compose-refs";
import { Search, X } from "lucide-react";
import {
  type ChangeEvent,
  type JSX,
  type KeyboardEvent,
  useMemo,
  useRef,
  useState,
} from "react";
import { FieldAction } from "./FieldAction";
import { useFieldControl } from "./field-context";
import { Input, type InputProps } from "./Input";
import { isComposing } from "./keyboard";

export type SearchFieldProps = Omit<
  InputProps,
  "type" | "value" | "defaultValue" | "leading" | "trailing"
> &
  Readonly<{
    value?: string;
    defaultValue?: string;
    /** Called on typing and on clear (Escape or the Clear button); a controlled field must update `value` from it. */
    onValueChange?: (value: string) => void;
    clearLabel?: string;
  }>;

/*
 * Escape clears the field when it has a value, and stops there; on an empty
 * field Escape bubbles so a dialog or menu can close. Radix layers see Escape
 * on the document in the capture phase, before this handler, so a dialog that
 * holds a SearchField skips dismissal for a target carrying
 * data-escape-clears by calling preventDefault in onEscapeKeyDown. The clear
 * therefore ignores a preventDefault made before it; only the caller's own
 * onKeyDown can cancel it.
 */
export function SearchField({
  value,
  defaultValue = "",
  onValueChange,
  onChange,
  onKeyDown,
  clearLabel = "Clear search",
  disabled,
  readOnly,
  ref,
  controlClassName,
  ...props
}: SearchFieldProps): JSX.Element {
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const current = value ?? uncontrolled;
  const inputRef = useRef<HTMLInputElement>(null);
  const composedRef = useMemo(() => composeRefs(inputRef, ref), [ref]);
  const state = useFieldControl({ disabled, readOnly });
  // A controlled field without onValueChange cannot be cleared, so it lets Escape through.
  const canClear = value === undefined || onValueChange !== undefined;
  const clearable =
    canClear && current !== "" && !state.disabled && !state.readOnly;

  const update = (next: string) => {
    if (value === undefined) {
      setUncontrolled(next);
    }
    onValueChange?.(next);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const preventedBefore = event.isDefaultPrevented();
    onKeyDown?.(event);
    const callerCancelled = !preventedBefore && event.isDefaultPrevented();
    if (
      callerCancelled ||
      event.key !== "Escape" ||
      !clearable ||
      isComposing(event)
    ) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    update("");
  };

  return (
    <Input
      ref={composedRef}
      type="search"
      value={current}
      disabled={disabled}
      readOnly={readOnly}
      data-escape-clears={clearable ? "" : undefined}
      onChange={(event: ChangeEvent<HTMLInputElement>) => {
        onChange?.(event);
        update(event.target.value);
      }}
      onKeyDown={handleKeyDown}
      leading={<Search aria-hidden />}
      trailing={
        clearable ? (
          <FieldAction
            label={clearLabel}
            onClick={() => {
              update("");
              inputRef.current?.focus();
            }}
          >
            <X aria-hidden />
          </FieldAction>
        ) : null
      }
      controlClassName={cn(
        "ui:[&::-webkit-search-cancel-button]:appearance-none ui:[&::-webkit-search-decoration]:appearance-none",
        controlClassName,
      )}
      {...props}
    />
  );
}
