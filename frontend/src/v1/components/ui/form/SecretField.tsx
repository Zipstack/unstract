import { composeRefs } from "@v1/lib/compose-refs";
import { Copy, Eye, EyeOff } from "lucide-react";
import { type JSX, useMemo, useRef, useState } from "react";
import { FieldAction } from "./FieldAction";
import { useFieldContext } from "./field-context";
import { Input, type InputProps } from "./Input";

export type CopyResult =
  | Readonly<{ status: "copied" }>
  | Readonly<{ status: "failed"; error: unknown }>;

export type SecretFieldProps = Omit<InputProps, "type" | "trailing"> &
  Readonly<{
    /*
     * The toast seam: the caller raises the confirmation (or the failure) on
     * the toast contract. Replace with a direct toast call once the toast
     * component exists.
     */
    onCopyResult?: (result: CopyResult) => void;
    revealLabel?: string;
    copyLabel?: string;
  }>;

/** A masked value, such as an API key, with Reveal and Copy. Copy writes the real value, masked or not. */
export function SecretField({
  onCopyResult,
  revealLabel = "Reveal",
  copyLabel = "Copy",
  disabled,
  ref,
  autoComplete = "off",
  ...props
}: SecretFieldProps): JSX.Element {
  const field = useFieldContext();
  const [revealed, setRevealed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const composedRef = useMemo(() => composeRefs(inputRef, ref), [ref]);
  const isDisabled = disabled ?? field?.disabled ?? false;

  // Read from the node, so a controlled and an uncontrolled field copy the same way.
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(inputRef.current?.value ?? "");
      onCopyResult?.({ status: "copied" });
    } catch (error: unknown) {
      // navigator.clipboard is undefined outside a secure context, or the write is refused.
      onCopyResult?.({ status: "failed", error });
    }
  };

  return (
    <Input
      ref={composedRef}
      type={revealed ? "text" : "password"}
      disabled={disabled}
      autoComplete={autoComplete}
      spellCheck={false}
      autoCapitalize="off"
      trailing={
        <>
          <FieldAction
            label={revealLabel}
            aria-pressed={revealed}
            disabled={isDisabled}
            onClick={() => setRevealed((shown) => !shown)}
          >
            {revealed ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
          </FieldAction>
          <FieldAction
            label={copyLabel}
            disabled={isDisabled}
            onClick={() => {
              void copy();
            }}
          >
            <Copy aria-hidden />
          </FieldAction>
        </>
      }
      {...props}
    />
  );
}
