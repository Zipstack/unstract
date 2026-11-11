import { cn } from "@v1/lib/cn";
import { composeRefs } from "@v1/lib/merge-refs";
import { Search, X } from "lucide-react";
import {
  type ChangeEvent,
  type JSX,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { FieldAction } from "./FieldAction";
import { useFieldControl } from "./field-context";
import { Input, type InputProps } from "./Input";
import { isComposing } from "./keyboard";

// No onChange: onValueChange is the one way to hear a change, so a controlled
// field cannot be wired in a way that silently loses Clear and Escape.
export type SearchFieldProps = Omit<
  InputProps,
  "type" | "value" | "defaultValue" | "onChange" | "leading" | "trailing"
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
 * on the document in the capture phase, before this handler, so an overlay
 * that holds a SearchField calls preventDefault in onEscapeKeyDown when
 * `isEscapeClearTarget(event)` (keyboard.ts) is true. The clear
 * therefore ignores a preventDefault made before it; only a preventDefault
 * called from the caller's own onKeyDown cancels it.
 */
/**
 * Runs the caller's onKeyDown and reports whether it called preventDefault
 * itself. A Radix layer may have prevented the event already, so the event's
 * prevented flag alone cannot say who cancelled it.
 */
function callerPreventsDefault(
  event: KeyboardEvent<HTMLInputElement>,
  onKeyDown: SearchFieldProps["onKeyDown"],
): boolean {
  if (!onKeyDown) {
    return false;
  }
  const preventDefault = event.preventDefault;
  let called = false;
  // ponytail: wraps the method for the call only, then puts the original back.
  event.preventDefault = () => {
    called = true;
    preventDefault.call(event);
  };
  try {
    onKeyDown(event);
  } finally {
    event.preventDefault = preventDefault;
  }
  return called;
}

export function SearchField({
  value,
  defaultValue = "",
  onValueChange,
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

  // A form reset restores the DOM value, not this state, so restore it here.
  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form || value !== undefined) {
      return undefined;
    }
    const onReset = () => setUncontrolled(defaultValue);
    form.addEventListener("reset", onReset);
    return () => form.removeEventListener("reset", onReset);
  }, [value, defaultValue]);

  const update = (next: string) => {
    if (value === undefined) {
      setUncontrolled(next);
    }
    onValueChange?.(next);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const callerCancelled = callerPreventsDefault(event, onKeyDown);
    if (callerCancelled || event.key !== "Escape" || isComposing(event)) {
      return;
    }
    if (current !== "" && !state.disabled && !state.readOnly) {
      // Chromium and WebKit clear a non-empty type="search" input on Escape
      // themselves, bypassing `update`; only this component clears it.
      event.preventDefault();
    }
    if (!clearable) {
      return;
    }
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
