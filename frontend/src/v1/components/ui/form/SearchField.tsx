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
import { useFieldContext } from "./field-context";
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
 * field Escape bubbles so a dialog or menu can close. Radix layers listen for
 * Escape on the document in the capture phase, before this handler runs, so a
 * dialog that holds a SearchField must skip dismissal for a target that
 * carries data-escape-clears.
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
  const field = useFieldContext();
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const current = value ?? uncontrolled;
  const inputRef = useRef<HTMLInputElement>(null);
  const composedRef = useMemo(() => composeRefs(inputRef, ref), [ref]);
  const locked =
    (disabled ?? field?.disabled ?? false) ||
    (readOnly ?? field?.readOnly ?? false);
  const clearable = current !== "" && !locked;

  const update = (next: string) => {
    if (value === undefined) {
      setUncontrolled(next);
    }
    onValueChange?.(next);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    onKeyDown?.(event);
    if (
      event.defaultPrevented ||
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
