import { cn } from "@v1/lib/cn";
import { Label as LabelPrimitive } from "radix-ui";
import { type JSX, type ReactNode, useId } from "react";

/** Text style of a control's label; shared by every toggle and the slider. */
export const CONTROL_LABEL_CLASS =
  "ui:text-body-small ui:font-medium ui:text-foreground ui:select-none ui:leading-4 ui:data-disabled:opacity-50";

/** Text style of a control's description. */
export const CONTROL_DESCRIPTION_CLASS =
  "ui:text-caption ui:text-muted-foreground";

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
 * neither, only the control renders.
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
  const hasDescription = description !== undefined && description !== null;
  const hasLabel = label !== undefined && label !== null;
  const descriptionId = hasDescription ? `${id}-description` : undefined;
  return (
    <div
      data-slot="control-row"
      className={cn("ui:flex ui:items-start ui:gap-2", className)}
    >
      {control({ id, describedBy: descriptionId })}
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
