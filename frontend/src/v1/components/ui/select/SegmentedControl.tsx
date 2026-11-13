import { cn } from "@v1/lib/cn";
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";
import { type JSX, type ReactNode, useState } from "react";

export type SegmentedOption = Readonly<{
  value: string;
  /** The item's accessible name, always shown; `icon` sits before it. */
  label: string;
  /** A lucide icon, decorative, sized 16. */
  icon?: ReactNode;
  disabled?: boolean;
}>;

export type SegmentedControlProps = Readonly<{
  /** 2 to 5 options; any other count throws during render. */
  options: readonly SegmentedOption[];
  value?: string;
  /** Defaults to the first enabled option's value. */
  defaultValue?: string;
  /** Called only with a new, non-empty value. */
  onValueChange?: (value: string) => void;
  /** Disables every item. */
  disabled?: boolean;
  /** Sets `aria-invalid` and `data-invalid` on the group, which draws a destructive outline. */
  invalid?: boolean;
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
  /** Classes for the group. */
  className?: string;
}>;

// The invalid outline sits outside the track, so the pills do not move.
// `outline-1` sets the style too (Tailwind 4), so no bare `outline`, which
// tailwind-merge would drop as a conflict.
const GROUP_CLASS =
  "ui:inline-flex ui:h-8 ui:items-center ui:rounded-md ui:bg-muted ui:p-0.5 ui:data-invalid:outline-1 ui:data-invalid:outline-destructive";

const ITEM_CLASS =
  "ui:inline-flex ui:h-7 ui:cursor-pointer ui:items-center ui:justify-center ui:gap-1.5 ui:rounded-sm ui:border-0 ui:bg-transparent ui:px-3 ui:text-body-small ui:font-medium ui:text-muted-foreground ui:outline-none ui:focus-visible:focus-ring ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:data-[state=on]:bg-background ui:data-[state=on]:text-foreground ui:data-[state=on]:shadow-sm";

/**
 * Exactly one of 2 to 5 options, always selected, on Radix ToggleGroup
 * (`type="single"`, which renders a `radiogroup` of `radio` items with
 * `aria-checked`; horizontal roving focus): ArrowLeft/ArrowRight move
 * focus (skipping disabled items, looping), Home/End jump, Enter/Space
 * select. Clicking the selected item keeps it selected. Throws during
 * render for fewer than 2 or more than 5 options: past five, use `Select`.
 */
export function SegmentedControl({
  options,
  value,
  defaultValue,
  onValueChange,
  disabled,
  invalid,
  id,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
  "aria-describedby": ariaDescribedBy,
  className,
}: SegmentedControlProps): JSX.Element {
  if (options.length < 2 || options.length > 5) {
    throw new Error("SegmentedControl needs 2 to 5 options");
  }
  const [uncontrolled, setUncontrolled] = useState(
    () =>
      defaultValue ?? options.find((option) => !option.disabled)?.value ?? "",
  );
  const current = value ?? uncontrolled;
  const select = (next: string) => {
    // Radix sends "" when the pressed item is pressed again; one stays selected.
    if (next === "") {
      return;
    }
    setUncontrolled(next);
    onValueChange?.(next);
  };
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      orientation="horizontal"
      value={current}
      onValueChange={select}
      disabled={disabled}
      id={id}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledBy}
      aria-describedby={ariaDescribedBy}
      aria-invalid={invalid || undefined}
      data-invalid={invalid ? "" : undefined}
      data-slot="segmented-control"
      className={cn(GROUP_CLASS, className)}
    >
      {options.map((option) => (
        <ToggleGroupPrimitive.Item
          key={option.value}
          value={option.value}
          // Radix also disables every item when the group is disabled.
          disabled={option.disabled}
          data-slot="segmented-item"
          className={ITEM_CLASS}
        >
          {option.icon ? (
            <span
              aria-hidden
              data-slot="segmented-icon"
              className="ui:flex ui:[&>svg]:size-4"
            >
              {option.icon}
            </span>
          ) : null}
          {option.label}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
}
