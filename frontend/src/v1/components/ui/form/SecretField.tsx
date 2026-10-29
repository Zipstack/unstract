import { composeRefs } from "@v1/lib/compose-refs";
import { Copy, Eye, EyeOff } from "lucide-react";
import { type JSX, useMemo, useRef, useState } from "react";
import { FieldAction } from "./FieldAction";
import { useFieldControl } from "./field-context";
import { Input, type InputProps } from "./Input";

export type CopyResult =
  | Readonly<{ status: "copied" }>
  | Readonly<{ status: "empty" }>
  | Readonly<{ status: "failed"; error: unknown }>;

export type SecretFieldProps = Omit<
  InputProps,
  "type" | "trailing" | "autoComplete" | "spellCheck" | "autoCapitalize"
> &
  Readonly<{
    /*
     * The toast seam: the caller raises the confirmation (or the failure) on
     * the toast contract. Required, so a failed copy is never silent. Replace
     * with a direct toast call once the toast component exists.
     */
    onCopyResult: (result: CopyResult) => void;
    revealLabel?: string;
    copyLabel?: string;
  }>;

/** Reads the node, so a controlled and an uncontrolled field copy the same way. */
async function copyValue(input: HTMLInputElement | null): Promise<CopyResult> {
  const text = input?.value ?? "";
  if (text === "") {
    return { status: "empty" };
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch (error: unknown) {
    // navigator.clipboard is undefined outside a secure context, or the write is refused.
    return { status: "failed", error };
  }
  return { status: "copied" };
}

/*
 * A masked value, such as an API key, with Reveal and Copy. Copy writes the
 * real value, masked or not. Both stay usable when the field is read-only,
 * the usual way to show a key, and are disabled with the field.
 */
export function SecretField({
  onCopyResult,
  revealLabel = "Reveal",
  copyLabel = "Copy",
  disabled,
  ref,
  ...props
}: SecretFieldProps): JSX.Element {
  const [revealed, setRevealed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const composedRef = useMemo(() => composeRefs(inputRef, ref), [ref]);
  const state = useFieldControl({ disabled });

  return (
    <Input
      ref={composedRef}
      disabled={disabled}
      trailing={
        <>
          <FieldAction
            label={revealLabel}
            aria-pressed={revealed}
            disabled={state.disabled}
            onClick={() => setRevealed((shown) => !shown)}
          >
            {revealed ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
          </FieldAction>
          <FieldAction
            label={copyLabel}
            disabled={state.disabled}
            onClick={() => {
              void copyValue(inputRef.current).then(onCopyResult);
            }}
          >
            <Copy aria-hidden />
          </FieldAction>
        </>
      }
      {...props}
      // After the spread, so a caller cannot turn masking or the privacy hints off.
      type={revealed ? "text" : "password"}
      autoComplete="new-password"
      spellCheck={false}
      autoCapitalize="off"
      autoCorrect="off"
      data-1p-ignore=""
      data-lpignore="true"
    />
  );
}
