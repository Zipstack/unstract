import { Check, Minus } from "lucide-react";
import { Checkbox as CheckboxPrimitive } from "radix-ui";
import type { ComponentProps, JSX, ReactNode } from "react";
import { ControlRow } from "./ControlRow";

export type CheckboxProps = Omit<
  ComponentProps<typeof CheckboxPrimitive.Root>,
  "asChild" | "children"
> &
  Readonly<{
    label?: ReactNode;
    description?: ReactNode;
    /** Class for the row, not the box. */
    className?: string;
  }>;

/**
 * A 16px checkbox with an optional label and description. The mixed state is
 * controlled only (`checked="indeterminate"`) and shows a minus. The icon is
 * the indicator itself (`asChild`), so its parent is the button and v0's
 * `svg.lucide` sizing rule does not reach it.
 */
export function Checkbox({
  label,
  description,
  className,
  id,
  disabled,
  checked,
  "aria-describedby": ariaDescribedBy,
  ...props
}: CheckboxProps): JSX.Element {
  const Icon = checked === "indeterminate" ? Minus : Check;
  return (
    <ControlRow
      id={id}
      label={label}
      description={description}
      disabled={disabled}
      className={className}
      control={({ id: controlId, describedBy }) => (
        <CheckboxPrimitive.Root
          id={controlId}
          data-slot="checkbox"
          disabled={disabled}
          checked={checked}
          aria-describedby={
            [ariaDescribedBy, describedBy].filter(Boolean).join(" ") ||
            undefined
          }
          className="ui:peer ui:size-4 ui:shrink-0 ui:cursor-pointer ui:rounded-sm ui:border ui:border-input ui:bg-background ui:text-primary-foreground ui:focus-visible:focus-ring ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:data-[state=checked]:border-primary ui:data-[state=checked]:bg-primary ui:data-[state=indeterminate]:border-primary ui:data-[state=indeterminate]:bg-primary"
          {...props}
        >
          <CheckboxPrimitive.Indicator asChild>
            <Icon className="ui:size-3.5" aria-hidden />
          </CheckboxPrimitive.Indicator>
        </CheckboxPrimitive.Root>
      )}
    />
  );
}
