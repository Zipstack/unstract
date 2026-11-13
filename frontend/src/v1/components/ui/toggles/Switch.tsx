import { Switch as SwitchPrimitive } from "radix-ui";
import type { ComponentProps, JSX, ReactNode } from "react";
import { ControlRow } from "./ControlRow";

export type SwitchProps = Omit<
  ComponentProps<typeof SwitchPrimitive.Root>,
  "asChild" | "children"
> &
  Readonly<{
    label?: ReactNode;
    description?: ReactNode;
    /** Class for the row, not the switch. */
    className?: string;
  }>;

/**
 * A 20 by 36 on/off switch with an optional label and description. The thumb
 * is 16px and travels 16px (36 less two 2px borders less the thumb).
 */
export function Switch({
  label,
  description,
  className,
  id,
  disabled,
  "aria-describedby": ariaDescribedBy,
  ...props
}: SwitchProps): JSX.Element {
  return (
    <ControlRow
      id={id}
      label={label}
      description={description}
      disabled={disabled}
      className={className}
      control={({ id: controlId, describedBy }) => (
        <SwitchPrimitive.Root
          id={controlId}
          data-slot="switch"
          disabled={disabled}
          aria-describedby={
            [ariaDescribedBy, describedBy].filter(Boolean).join(" ") ||
            undefined
          }
          className="ui:peer ui:inline-flex ui:h-5 ui:w-9 ui:shrink-0 ui:cursor-pointer ui:items-center ui:rounded-full ui:border-2 ui:border-transparent ui:bg-input ui:transition-colors ui:focus-visible:focus-ring ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:data-[state=checked]:bg-primary"
          {...props}
        >
          <SwitchPrimitive.Thumb
            data-slot="switch-thumb"
            className="ui:pointer-events-none ui:block ui:size-4 ui:rounded-full ui:bg-background ui:shadow-sm ui:transition-transform ui:data-[state=checked]:translate-x-4 ui:data-[state=unchecked]:translate-x-0"
          />
        </SwitchPrimitive.Root>
      )}
    />
  );
}
