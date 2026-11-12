import { cn } from "@v1/lib/cn";
import { mergeRefs } from "@v1/lib/merge-refs";
import { Search, X } from "lucide-react";
import {
  type ChangeEvent,
  type JSX,
  type KeyboardEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { FieldAction } from "./FieldAction";
import { useFieldControl } from "./field-context";
import { Input, type InputProps } from "./Input";
import { isComposing } from "./keyboard";

// onChange is left out of the type: onValueChange is the documented way to
// hear a change. A spread (`{...field}`, `{...register()}`) still carries one,
// and the field calls it on typing and on clear. A spread onChange without a
// value (`{...register()}`) leaves the input uncontrolled, so the value the
// form library writes to the DOM stays on screen.
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
  // Wraps the method for the call only, then puts the original back.
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

/**
 * A search box with a Clear button. Escape clears the field when it has a
 * value, and stops there; on an empty field Escape bubbles so a dialog or menu
 * can close. Radix layers see Escape on the document in the capture phase,
 * before this handler, so an overlay that holds a SearchField calls
 * preventDefault in onEscapeKeyDown when `isEscapeClearTarget(event)`
 * (keyboard.ts) is true. The clear therefore ignores a preventDefault made
 * before it; only a preventDefault called from the caller's own onKeyDown
 * cancels it.
 */
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
  ...rest
}: SearchFieldProps): JSX.Element {
  const { onChange: spreadOnChange, ...props } = rest as typeof rest & {
    onChange?: InputProps["onChange"];
  };
  // `{...register()}`: the form library sets the DOM value itself (defaults,
  // setValue, reset), so the input is left uncontrolled and `uncontrolled`
  // follows the DOM instead of driving it.
  const domOwned = value === undefined && spreadOnChange !== undefined;
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const current = value ?? uncontrolled;
  const inputRef = useRef<HTMLInputElement>(null);
  const composedRef = useMemo(() => mergeRefs(inputRef, ref), [ref]);
  const onValueChangeRef = useRef(onValueChange);
  const state = useFieldControl({ disabled, readOnly });

  useLayoutEffect(() => {
    onValueChangeRef.current = onValueChange;
  });

  // Pick up a value written straight to the DOM, so the Clear button matches it.
  useLayoutEffect(() => {
    const input = inputRef.current;
    if (domOwned && input && input.value !== uncontrolled) {
      setUncontrolled(input.value);
    }
  });

  // A controlled field without onValueChange or a spread onChange cannot be
  // cleared, so it lets Escape through.
  const canClear =
    value === undefined ||
    onValueChange !== undefined ||
    spreadOnChange !== undefined;
  const clearable =
    canClear && current !== "" && !state.disabled && !state.readOnly;

  // A form reset restores the DOM value, not this state, so restore it here.
  // A listener later in the dispatch (React's onReset) may cancel the reset,
  // so wait for the dispatch to finish and check.
  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form || value !== undefined) {
      return undefined;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onReset = (event: Event) => {
      timer = setTimeout(() => {
        if (event.defaultPrevented) {
          return;
        }
        const restored = domOwned
          ? (inputRef.current?.value ?? defaultValue)
          : defaultValue;
        setUncontrolled(restored);
        onValueChangeRef.current?.(restored);
      });
    };
    form.addEventListener("reset", onReset);
    return () => {
      form.removeEventListener("reset", onReset);
      clearTimeout(timer);
    };
  }, [value, defaultValue, domOwned]);

  const update = (next: string) => {
    if (value === undefined) {
      setUncontrolled(next);
    }
    onValueChange?.(next);
  };

  const clear = () => {
    const input = inputRef.current;
    if (!(spreadOnChange && input)) {
      update("");
      return;
    }
    // A spread onChange reads a real event (react-hook-form's register reads
    // event.target), so clear the way typing does: set the DOM value and fire
    // input, which reaches the onChange below.
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set?.call(input, "");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const callerCancelled = callerPreventsDefault(event, onKeyDown);
    if (callerCancelled || event.key !== "Escape" || isComposing(event)) {
      return;
    }
    // A DOM-owned value may have been set (setValue) since the last render.
    const shown = domOwned ? event.currentTarget.value : current;
    const editable = shown !== "" && !state.disabled && !state.readOnly;
    if (editable) {
      // Chromium and WebKit clear a non-empty type="search" input on Escape
      // themselves, bypassing `update`; only this component clears it.
      event.preventDefault();
    }
    if (!(canClear && editable)) {
      return;
    }
    event.stopPropagation();
    clear();
  };

  return (
    <Input
      // First, so nothing in a spread replaces the handlers this field owns.
      {...props}
      ref={composedRef}
      type="search"
      {...(domOwned ? { defaultValue } : { value: current })}
      disabled={disabled}
      readOnly={readOnly}
      // Marks a field Escape can clear; isEscapeClearTarget reads the live
      // value, which a form library may have written without a render.
      data-escape-clears={
        canClear && !state.disabled && !state.readOnly ? "" : undefined
      }
      onChange={(event: ChangeEvent<HTMLInputElement>) => {
        update(event.target.value);
        spreadOnChange?.(event);
      }}
      onKeyDown={handleKeyDown}
      leading={<Search aria-hidden />}
      trailing={
        clearable ? (
          <FieldAction
            label={clearLabel}
            onClick={() => {
              clear();
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
    />
  );
}
