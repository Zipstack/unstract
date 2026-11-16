import { cn } from "@v1/lib/cn";
import { Check, Minus } from "lucide-react";
import { Checkbox as CheckboxPrimitive } from "radix-ui";
import type { JSX } from "react";

/*
 * SEAM: the one place the table gets its checkbox. It stands in for P1-T05's
 * `Checkbox` (`@v1/components/ui/toggles`, #2462, not on main yet) with the
 * same props, so the swap is this file only:
 *
 *   export { Checkbox as SelectCheckbox } from "@v1/components/ui/toggles";
 *
 * Mixed is controlled only (`checked="indeterminate"`, `aria-checked="mixed"`),
 * and with no visible label `aria-label` is required.
 */

export type SelectCheckboxProps = Readonly<{
  checked: boolean | "indeterminate";
  onCheckedChange: (checked: boolean | "indeterminate") => void;
  "aria-label": string;
  disabled?: boolean;
  tabIndex?: number;
  className?: string;
}>;

export function SelectCheckbox({
  checked,
  className,
  ...props
}: SelectCheckboxProps): JSX.Element {
  const Icon = checked === "indeterminate" ? Minus : Check;
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      checked={checked}
      className={cn(
        "ui:peer ui:inline-flex ui:size-4 ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-sm ui:border ui:border-solid ui:border-input ui:bg-background ui:p-0 ui:text-primary-foreground ui:focus-visible:focus-ring ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:data-[state=checked]:border-primary ui:data-[state=checked]:bg-primary ui:data-[state=indeterminate]:border-primary ui:data-[state=indeterminate]:bg-primary",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator asChild>
        <Icon className="ui:size-3.5" aria-hidden />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
