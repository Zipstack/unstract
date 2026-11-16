import { cn } from "@v1/lib/cn";
import { type CopyResult, copyText } from "@v1/lib/code/clipboard";
import { toast } from "@v1/lib/notify";
import { Check, Copy } from "lucide-react";
import {
  type ComponentProps,
  type JSX,
  useEffect,
  useRef,
  useState,
} from "react";
import { BUTTON_BASE } from "./CodeLines";

/** How long the button shows its result before returning to "Copy". */
export const COPY_FEEDBACK_MS = 2000;

const INLINE_MESSAGE: Readonly<Record<CopyResult, string>> = {
  copied: "Copied",
  failed: "Copy failed",
  unavailable: "Copy unavailable",
};

export type CopyButtonProps = Omit<
  ComponentProps<"button">,
  "onClick" | "children" | "type" | "onCopy"
> &
  Readonly<{
    /** The text to copy, or a function read at click time (for large values). */
    text: string | (() => string);
    /** The accessible name, and the visible text when `showLabel` is set. */
    label?: string;
    /** Shows `label` beside the icon ("Copy code"); icon-only by default. */
    showLabel?: boolean;
    /**
     * Confirms through the v1 toast (`toast.success` / `toast.error` from
     * `@v1/lib/notify`). On by default; turn it off where many copy controls
     * sit together and the inline confirmation is enough.
     */
    toastOnCopy?: boolean;
    /** The success toast's title. */
    copiedMessage?: string;
    /** Called with the outcome of every attempt. */
    onCopy?: (result: CopyResult) => void;
  }>;

/**
 * The one copy control for v1. Every attempt gives inline feedback (a check
 * on success, a red icon on failure, and with `showLabel` the label names the
 * outcome) and, unless
 * `toastOnCopy` is off, a toast. With the toast off, a polite live region
 * announces the result instead, so screen readers hear it exactly once.
 */
export function CopyButton({
  text,
  label = "Copy",
  showLabel = false,
  toastOnCopy = true,
  copiedMessage = "Copied to clipboard",
  onCopy,
  className,
  disabled,
  ...props
}: CopyButtonProps): JSX.Element {
  const [result, setResult] = useState<CopyResult | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearTimeout(timer.current);
    };
  }, []);

  const copy = async () => {
    const outcome = await copyText(typeof text === "function" ? text() : text);
    if (toastOnCopy) {
      if (outcome === "copied") {
        toast.success(copiedMessage);
      } else if (outcome === "unavailable") {
        toast.error("Copy is not available", {
          description: "This browser does not allow clipboard access here.",
        });
      } else {
        toast.error("Could not copy", {
          description: "Try again, or select the text and copy it.",
        });
      }
    }
    // Unmounted while the clipboard was busy: no inline state, and no timer
    // left behind after the cleanup has run. The caller still hears the result.
    if (mounted.current) {
      setResult(outcome);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setResult(null), COPY_FEEDBACK_MS);
    }
    onCopy?.(outcome);
  };

  const Icon = result === "copied" ? Check : Copy;
  const visible = result ? INLINE_MESSAGE[result] : label;
  return (
    <span className="ui:inline-flex" data-slot="copy-button">
      <button
        type="button"
        aria-label={showLabel ? undefined : label}
        data-state={result ?? "idle"}
        disabled={disabled}
        onClick={() => {
          void copy();
        }}
        className={cn(
          BUTTON_BASE,
          "ui:shrink-0 ui:justify-center ui:gap-1.5 ui:disabled:cursor-not-allowed ui:disabled:opacity-50",
          showLabel
            ? "ui:h-7 ui:px-2 ui:text-body-small ui:font-medium"
            : "ui:size-7",
          result === "copied" && "ui:text-success ui:hover:text-success",
          (result === "failed" || result === "unavailable") &&
            "ui:text-destructive ui:hover:text-destructive",
          className,
        )}
        {...props}
      >
        <Icon aria-hidden className="ui:size-4" />
        {showLabel ? <span>{visible}</span> : null}
      </button>
      {toastOnCopy ? null : (
        <output className="ui:sr-only">
          {result ? INLINE_MESSAGE[result] : ""}
        </output>
      )}
    </span>
  );
}
