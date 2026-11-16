import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX } from "react";

export type FieldActionProps = Omit<ComponentProps<"button">, "aria-label"> &
  Readonly<{
    /** The accessible name; also shown as the tooltip, since the button shows only an icon. */
    label: string;
  }>;

/** An icon button inside a field frame, such as Reveal, Copy or Clear. */
export function FieldAction({
  label,
  className,
  type = "button",
  ...props
}: FieldActionProps): JSX.Element {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      data-slot="field-action"
      className={cn(
        "ui:inline-flex ui:size-6 ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:hover:bg-accent ui:hover:text-foreground ui:focus-visible:focus-ring ui:aria-pressed:text-foreground ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:[&>svg]:size-4",
        className,
      )}
      {...props}
    />
  );
}
