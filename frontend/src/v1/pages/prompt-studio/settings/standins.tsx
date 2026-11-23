/*
 * Local stand-ins for primitives that are still open. Each keeps the prop
 * shape its replacement takes, so the swap is an import change.
 */
import { fieldFrameVariants, useFieldControl } from "@v1/components/ui/form";
import { cn } from "@v1/lib/cn";
import type { ComponentProps, JSX, ReactNode } from "react";

export type SelectOption = Readonly<{
  value: string;
  label: string;
  disabled?: boolean;
}>;

export type SelectFieldProps = Omit<
  ComponentProps<"select">,
  "children" | "onChange" | "value"
> &
  Readonly<{
    value: string;
    onChange: (value: string) => void;
    options: readonly SelectOption[];
    placeholder: string;
  }>;

/**
 * A select inside a Field: takes the Field's id and description.
 * ponytail: native select until P1-T04's Select lands; swap the import.
 */
export function SelectField({
  value,
  onChange,
  options,
  placeholder,
  disabled,
  className,
  ...props
}: SelectFieldProps): JSX.Element {
  const control = useFieldControl({ disabled });
  return (
    <select
      {...props}
      id={control.id}
      aria-describedby={control["aria-describedby"]}
      aria-invalid={control["aria-invalid"]}
      disabled={control.disabled}
      data-invalid={control.invalid ? "" : undefined}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={cn(fieldFrameVariants({ focus: "self" }), className)}
    >
      <option value="" disabled>
        {placeholder}
      </option>
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/**
 * The Add/Edit LLM Profile surface (frame D10 draws a dialog).
 * ponytail: an in-place panel until P1-T07's Dialog lands; swap this for
 * `Dialog` with the same title, open and onClose.
 */
export function ProfileDialog({
  title,
  children,
}: Readonly<{
  title: string;
  /** The Dialog closes on Escape and the close button; the panel has neither. */
  onClose: () => void;
  children: ReactNode;
}>): JSX.Element {
  return (
    <section
      aria-label={title}
      data-slot="profile-dialog"
      className="ui:grid ui:gap-4"
    >
      <h3 className="ui:text-section-title ui:font-semibold ui:text-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

export type DestructiveConfirm = Readonly<{
  title: string;
  description: string;
  confirmLabel: string;
}>;

/**
 * Asks before a destructive action.
 * ponytail: the browser's confirm until P1-T07's `confirm()` lands; it takes
 * these options, so the swap is the import.
 */
export function confirmDestructive(
  options: DestructiveConfirm,
): Promise<boolean> {
  return Promise.resolve(
    window.confirm(`${options.title}\n\n${options.description}`),
  );
}
