import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { JSX } from "react";

const RemoveIcon = ACTION_ICONS.close;

export type ChipProps = Readonly<{
  label: string;
  /** Shows a remove button named "Remove {label}". */
  onRemove?: () => void;
  disabled?: boolean;
  className?: string;
}>;

/** A selected value in a MultiSelect, with an optional remove button. */
export function Chip({
  label,
  onRemove,
  disabled,
  className,
}: ChipProps): JSX.Element {
  return (
    <span
      data-slot="chip"
      className={cn(
        "ui:inline-flex ui:h-5 ui:max-w-full ui:items-center ui:gap-1 ui:rounded-sm ui:bg-muted ui:pl-1.75 ui:pr-0.5 ui:text-caption ui:font-medium ui:text-muted-foreground",
        className,
      )}
    >
      <span className="ui:truncate">{label}</span>
      {onRemove ? (
        <button
          type="button"
          aria-label={`Remove ${label}`}
          disabled={disabled}
          onClick={onRemove}
          className="ui:flex ui:size-4 ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:hover:bg-accent ui:hover:text-foreground ui:focus-visible:focus-ring"
        >
          <RemoveIcon aria-hidden className="ui:size-3" />
        </button>
      ) : null}
    </span>
  );
}
