import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { JSX } from "react";

const RemoveIcon = ACTION_ICONS.close;

export type ChipProps = Readonly<{
  label: string;
  /** Shows a remove button named "Remove {label}". */
  onRemove?: () => void;
  /**
   * Whether the remove button is a tab stop. Default true; false keeps it
   * clickable and named but out of the tab order, for a field whose keyboard
   * removes chips another way (MultiSelect: Backspace).
   */
  removeFocusable?: boolean;
  disabled?: boolean;
  className?: string;
}>;

/**
 * A selected value in a MultiSelect, with an optional remove button, which
 * `removeFocusable={false}` takes out of the tab order.
 */
export function Chip({
  label,
  onRemove,
  removeFocusable = true,
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
          tabIndex={removeFocusable ? undefined : -1}
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
