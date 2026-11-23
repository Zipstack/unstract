import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";

export type KbdProps = ComponentProps<"kbd">;

/** A keyboard-shortcut hint: one key per chip. */
export function Kbd({ className, ...props }: KbdProps): JSX.Element {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "ui:rounded-sm ui:border ui:border-border ui:bg-muted ui:px-1 ui:font-sans ui:text-caption ui:text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}
