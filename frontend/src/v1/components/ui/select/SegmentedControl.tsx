import { useFieldControl } from "@v1/components/ui/form";
import { cn } from "@v1/lib/cn";
import { ToggleGroup as ToggleGroupPrimitive } from "radix-ui";
import { type JSX, type ReactNode, type Ref, useState } from "react";

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
  /** Defaults to the first enabled option's value, also used when this names no enabled option. */
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
  /** The radiogroup element. */
  ref?: Ref<HTMLDivElement>;
}>;

// The track's edge is a 1px transparent border inside a 1px padding (2px in
// all, as before, so the pills do not move), which forced-colors mode (no
// backgrounds) paints; invalid colours it destructive. Not an outline: Radix's
// roving-focus root sets an inline `outline: none`, which beats any class.
const GROUP_CLASS =
  "ui:inline-flex ui:h-8 ui:items-center ui:rounded-md ui:border ui:border-transparent ui:bg-muted ui:p-px ui:data-invalid:border-destructive";

// The selected pill's background and shadow vanish in forced-colors mode, so
// it also takes a transparent 1px border, which that mode paints; the border
// replaces 1px of padding on each side (border-box), so nothing moves.
const ITEM_CLASS =
  "ui:inline-flex ui:h-7 ui:cursor-pointer ui:items-center ui:justify-center ui:gap-1.5 ui:rounded-sm ui:border-0 ui:bg-transparent ui:px-3 ui:data-[state=on]:border ui:data-[state=on]:border-transparent ui:data-[state=on]:px-2.75 ui:text-body-small ui:font-medium ui:text-muted-foreground ui:outline-none ui:focus-visible:focus-ring ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:data-[state=on]:bg-background ui:data-[state=on]:text-foreground ui:data-[state=on]:shadow-sm";

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
  ref,
}: SegmentedControlProps): JSX.Element {
  // Inside a Field: its id, description and state, and its label as the
  // group's name (a `<label for>` cannot name a radiogroup).
  const control = useFieldControl({
    id,
    "aria-describedby": ariaDescribedBy,
    invalid,
    disabled,
  });
  if (options.length < 2 || options.length > 5) {
    throw new Error("SegmentedControl needs 2 to 5 options");
  }
  // A default that names no enabled option would leave nothing selected, so
  // it falls back to the first enabled option, as no default does.
  const [uncontrolled, setUncontrolled] = useState(() => {
    const enabled = options.filter((option) => !option.disabled);
    const match = enabled.find((option) => option.value === defaultValue);
    return (match ?? enabled[0])?.value ?? "";
  });
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
      ref={ref}
      type="single"
      orientation="horizontal"
      value={current}
      onValueChange={select}
      disabled={control.disabled}
      id={control.id}
      aria-label={ariaLabel}
      aria-labelledby={
        ariaLabelledBy ?? (ariaLabel ? undefined : control.labelId)
      }
      aria-describedby={control["aria-describedby"]}
      aria-invalid={control["aria-invalid"]}
      data-invalid={control.invalid ? "" : undefined}
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
