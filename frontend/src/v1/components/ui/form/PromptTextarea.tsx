import { cn } from "@v1/lib/cn";
import { composeRefs } from "@v1/lib/compose-refs";
import {
  type JSX,
  type KeyboardEvent,
  useLayoutEffect,
  useMemo,
  useRef,
} from "react";
import { isComposing } from "./keyboard";
import { Textarea, type TextareaProps } from "./Textarea";

export type PromptTextareaProps = Omit<TextareaProps, "onSubmit"> &
  Readonly<{
    /** Called with the text on Enter. Without it, Enter inserts a line break as in a Textarea. */
    onSubmit?: (value: string) => void;
  }>;

function supportsFieldSizing(): boolean {
  return (
    typeof CSS !== "undefined" &&
    typeof CSS.supports === "function" &&
    CSS.supports("field-sizing", "content")
  );
}

/*
 * Where field-sizing is missing, size the textarea from its scrollHeight. The
 * height travels as a custom property that a class reads (styling rule S1);
 * min-h and max-h still clamp it.
 */
function fitToContent(element: HTMLTextAreaElement | null): void {
  if (!element || supportsFieldSizing()) {
    return;
  }
  element.style.setProperty("--prompt-height", "auto");
  element.style.setProperty("--prompt-height", `${element.scrollHeight}px`);
}

/** The prompt box: at least 104 tall, grows with its text to a maximum, then scrolls. Enter submits; Shift+Enter breaks the line. */
export function PromptTextarea({
  onSubmit,
  onKeyDown,
  onInput,
  value,
  ref,
  className,
  controlClassName,
  ...props
}: PromptTextareaProps): JSX.Element {
  const innerRef = useRef<HTMLTextAreaElement>(null);
  const textareaRef = useMemo(() => composeRefs(innerRef, ref), [ref]);

  // A controlled value can change without an input event (cleared after submit).
  // biome-ignore lint/correctness/useExhaustiveDependencies: value is the trigger, read through the ref.
  useLayoutEffect(() => {
    fitToContent(innerRef.current);
  }, [value]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    onKeyDown?.(event);
    if (
      event.defaultPrevented ||
      event.key !== "Enter" ||
      event.shiftKey ||
      !onSubmit ||
      isComposing(event)
    ) {
      return;
    }
    event.preventDefault();
    onSubmit(event.currentTarget.value);
  };

  return (
    <Textarea
      ref={textareaRef}
      value={value}
      onKeyDown={handleKeyDown}
      onInput={(event) => {
        onInput?.(event);
        fitToContent(event.currentTarget);
      }}
      className={cn("ui:min-h-26", className)}
      controlClassName={cn(
        // No Figma frame gives the maximum yet; 240 (ui:max-h-60) is a placeholder on the spacing scale.
        "ui:h-(--prompt-height) ui:max-h-60 ui:min-h-0 ui:resize-none ui:overflow-y-auto ui:field-sizing-content",
        controlClassName,
      )}
      {...props}
    />
  );
}
