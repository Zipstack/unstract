import { cn } from "@v1/lib/cn";
import { RadioGroup as RadioGroupPrimitive } from "radix-ui";
import {
  type ComponentProps,
  createContext,
  type JSX,
  type ReactNode,
  useContext,
  useId,
} from "react";
import {
  CONTROL_DESCRIPTION_CLASS,
  CONTROL_LABEL_CLASS,
  ControlRow,
} from "./ControlRow";

/** The group's `disabled`, so each Radio can dim its label with the group. */
const RadioGroupDisabledContext = createContext(false);

export type RadioGroupProps = Omit<
  ComponentProps<typeof RadioGroupPrimitive.Root>,
  "asChild"
> &
  Readonly<{
    /** Visible group name; rendered above the items and used as aria-labelledby. Without it pass aria-label. */
    label?: ReactNode;
    description?: ReactNode;
  }>;

/**
 * A set of radios with an optional heading and description. Arrow keys move
 * the selection and focus together, skipping disabled items. Pass
 * `orientation="horizontal"` to lay the items out in a row.
 */
export function RadioGroup({
  label,
  description,
  className,
  disabled = false,
  "aria-describedby": ariaDescribedBy,
  ...props
}: RadioGroupProps): JSX.Element {
  const id = useId();
  const hasLabel = label !== undefined && label !== null;
  const hasDescription = description !== undefined && description !== null;
  const labelId = `${id}-label`;
  const descriptionId = hasDescription ? `${id}-description` : undefined;
  return (
    <div data-slot="radio-group-field" className="ui:grid ui:gap-2">
      {hasLabel || hasDescription ? (
        <div className="ui:grid ui:gap-0.5">
          {hasLabel ? (
            <p
              id={labelId}
              data-disabled={disabled ? "" : undefined}
              className={CONTROL_LABEL_CLASS}
            >
              {label}
            </p>
          ) : null}
          {hasDescription ? (
            <p id={descriptionId} className={CONTROL_DESCRIPTION_CLASS}>
              {description}
            </p>
          ) : null}
        </div>
      ) : null}
      <RadioGroupDisabledContext.Provider value={disabled}>
        <RadioGroupPrimitive.Root
          data-slot="radio-group"
          disabled={disabled}
          aria-labelledby={hasLabel ? labelId : undefined}
          aria-describedby={
            [ariaDescribedBy, descriptionId].filter(Boolean).join(" ") ||
            undefined
          }
          className={cn(
            props.orientation === "horizontal"
              ? "ui:flex ui:flex-wrap ui:gap-4"
              : "ui:grid ui:gap-2",
            className,
          )}
          {...props}
        />
      </RadioGroupDisabledContext.Provider>
    </div>
  );
}

export type RadioProps = Omit<
  ComponentProps<typeof RadioGroupPrimitive.Item>,
  "asChild" | "children"
> &
  Readonly<{
    label?: ReactNode;
    description?: ReactNode;
    /** Class for the row, not the radio. */
    className?: string;
  }>;

/** A 14px radio with an optional label and description; use inside `RadioGroup`. */
export function Radio({
  label,
  description,
  className,
  id,
  disabled,
  "aria-describedby": ariaDescribedBy,
  ...props
}: RadioProps): JSX.Element {
  const groupDisabled = useContext(RadioGroupDisabledContext);
  return (
    <ControlRow
      id={id}
      label={label}
      description={description}
      disabled={disabled || groupDisabled}
      className={className}
      control={({ id: controlId, describedBy }) => (
        <RadioGroupPrimitive.Item
          id={controlId}
          data-slot="radio"
          disabled={disabled}
          aria-describedby={
            [ariaDescribedBy, describedBy].filter(Boolean).join(" ") ||
            undefined
          }
          className="ui:peer ui:size-3.5 ui:shrink-0 ui:cursor-pointer ui:rounded-full ui:border ui:border-input ui:bg-background ui:focus-visible:focus-ring ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:data-[state=checked]:border-primary"
          {...props}
        >
          <RadioGroupPrimitive.Indicator
            data-slot="radio-indicator"
            className="ui:flex ui:size-full ui:items-center ui:justify-center"
          >
            <span className="ui:size-1.5 ui:rounded-full ui:bg-primary" />
          </RadioGroupPrimitive.Indicator>
        </RadioGroupPrimitive.Item>
      )}
    />
  );
}
