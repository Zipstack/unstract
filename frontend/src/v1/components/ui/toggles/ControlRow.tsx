import { HELPER_TEXT_CLASS, LABEL_CLASS } from "@v1/components/ui/form";
import { cn } from "@v1/lib/cn";
import { Label as LabelPrimitive } from "radix-ui";
import { type JSX, type ReactNode, useId } from "react";

/**
 * Text style of a control's label, shared by every toggle and the slider: the
 * form `Label`'s, on a 20px line so each control centres on its first line.
 */
export const CONTROL_LABEL_CLASS = cn(LABEL_CLASS, "ui:leading-5");

/** Text style of a control's description: the form `HelperText`'s. */
export const CONTROL_DESCRIPTION_CLASS = HELPER_TEXT_CLASS;

/**
 * Every toggle needs an accessible name: a visible `label`, an `aria-label`
 * or an `aria-labelledby`. A `description` is not a name, and for a slider
 * neither are `thumbLabels`, which name the thumbs and not the group.
 */
export type Named =
  | Readonly<{ label: ReactNode }>
  | Readonly<{ "aria-label": string }>
  | Readonly<{ "aria-labelledby": string }>;

/** Whether a label or description renders: `false` and `""` count as absent. */
export function isPresent(node: ReactNode): boolean {
  return node !== null && node !== undefined && node !== false && node !== "";
}

export type ControlRowProps = Readonly<{
  /** The control. Receives `id` and `aria-describedby` through the render callback. */
  control: (ids: { id: string; describedBy: string | undefined }) => ReactNode;
  label?: ReactNode;
  description?: ReactNode;
  /** Caller's id for the control; generated when omitted. */
  id?: string;
  disabled?: boolean;
  className?: string;
}>;

/**
 * A control with its label and description beside it. The label is tied to
 * the control by `htmlFor`, the description by `aria-describedby`. With
 * neither, only the control renders. The control sits in a 20px box, the
 * label's line height, so every control centres on the label's first line.
 */
export function ControlRow({
  control,
  label,
  description,
  id: idProp,
  disabled,
  className,
}: ControlRowProps): JSX.Element {
  const generatedId = useId();
  const id = idProp ?? generatedId;
  const hasDescription = isPresent(description);
  const hasLabel = isPresent(label);
  const descriptionId = hasDescription ? `${id}-description` : undefined;
  return (
    <div
      data-slot="control-row"
      className={cn("ui:flex ui:items-start ui:gap-2", className)}
    >
      <span className="ui:flex ui:h-5 ui:shrink-0 ui:items-center">
        {control({ id, describedBy: descriptionId })}
      </span>
      {hasLabel || hasDescription ? (
        <div className="ui:grid ui:gap-0.5">
          {hasLabel ? (
            <LabelPrimitive.Root
              data-slot="control-label"
              htmlFor={id}
              data-disabled={disabled ? "" : undefined}
              className={CONTROL_LABEL_CLASS}
            >
              {label}
            </LabelPrimitive.Root>
          ) : null}
          {hasDescription ? (
            <p
              id={descriptionId}
              data-slot="control-description"
              className={CONTROL_DESCRIPTION_CLASS}
            >
              {description}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
