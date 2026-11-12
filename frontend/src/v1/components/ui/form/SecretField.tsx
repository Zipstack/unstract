import { type CopyResult, copyText } from "@v1/lib/code/clipboard";
import { mergeRefs } from "@v1/lib/merge-refs";
import { toast } from "@v1/lib/notify";
import { Copy, Eye, EyeOff } from "lucide-react";
import { type JSX, useMemo, useRef, useState } from "react";
import { FieldAction } from "./FieldAction";
import { useFieldControl } from "./field-context";
import { Input, type InputProps } from "./Input";

// onCopy is replaced: the native clipboard-event handler would otherwise widen
// the callback's argument to ClipboardEvent | CopyResult.
export type SecretFieldProps = Omit<
  InputProps,
  | "type"
  | "trailing"
  | "autoComplete"
  | "spellCheck"
  | "autoCapitalize"
  | "onCopy"
> &
  Readonly<{
    /** Hears each copy's outcome; the field raises the toast itself. Not called for an empty field. */
    onCopy?: (result: CopyResult) => void;
    revealLabel?: string;
    copyLabel?: string;
  }>;

/**
 * Copies the node's value, so a controlled and an uncontrolled field copy the
 * same way, and confirms through the toast as CopyButton does.
 */
async function copyValue(
  input: HTMLInputElement | null,
): Promise<CopyResult | undefined> {
  const text = input?.value ?? "";
  if (text === "") {
    toast.error("Nothing to copy");
    return undefined;
  }
  const outcome = await copyText(text);
  if (outcome === "copied") {
    toast.success("Copied to clipboard");
  } else if (outcome === "unavailable") {
    toast.error("Copy is not available", {
      description: "This browser does not allow clipboard access here.",
    });
  } else {
    toast.error("Could not copy", {
      description: "Try again, or select the text and copy it.",
    });
  }
  return outcome;
}

/*
 * A masked value, such as an API key, with Reveal and Copy. Copy writes the
 * real value, masked or not. Both stay usable when the field is read-only,
 * the usual way to show a key, and are disabled with the field.
 */
export function SecretField({
  onCopy,
  revealLabel = "Reveal",
  copyLabel = "Copy",
  disabled,
  ref,
  ...props
}: SecretFieldProps): JSX.Element {
  const [revealed, setRevealed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const composedRef = useMemo(() => mergeRefs(inputRef, ref), [ref]);
  const state = useFieldControl({ disabled });
  // A disabled field disables Reveal too, so a shown value is masked again.
  const shown = revealed && !state.disabled;

  return (
    <Input
      ref={composedRef}
      disabled={disabled}
      trailing={
        <>
          <FieldAction
            label={revealLabel}
            aria-pressed={shown}
            disabled={state.disabled}
            onClick={() => setRevealed((shown) => !shown)}
          >
            {shown ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
          </FieldAction>
          <FieldAction
            label={copyLabel}
            disabled={state.disabled}
            onClick={() => {
              void copyValue(inputRef.current).then(
                (outcome) => outcome && onCopy?.(outcome),
              );
            }}
          >
            <Copy aria-hidden />
          </FieldAction>
        </>
      }
      {...props}
      // After the spread, so a caller cannot turn masking or the privacy hints off.
      type={shown ? "text" : "password"}
      autoComplete="new-password"
      spellCheck={false}
      autoCapitalize="off"
      autoCorrect="off"
      data-1p-ignore=""
      data-lpignore="true"
    />
  );
}
