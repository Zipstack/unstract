import { cn } from "@v1/lib/cn";
import { Slider as SliderPrimitive } from "radix-ui";
import {
  type ComponentProps,
  type JSX,
  type ReactNode,
  useId,
  useState,
} from "react";
import {
  CONTROL_DESCRIPTION_CLASS,
  CONTROL_LABEL_CLASS,
  isPresent,
} from "./ControlRow";

export type SliderProps = Omit<
  ComponentProps<typeof SliderPrimitive.Root>,
  "asChild" | "children" | "orientation"
> &
  Readonly<{
    label?: ReactNode;
    description?: ReactNode;
    /** Accessible name per thumb when there is more than one, in order (e.g. ["Minimum", "Maximum"]); a single thumb takes `label`. */
    thumbLabels?: readonly string[];
    /** Spoken and, with `showValue`, shown value. Default `String(value)`. */
    formatValue?: (value: number) => string;
    /** Shows the formatted value(s) at the end of the label line. */
    showValue?: boolean;
    /** Class for the field (label line, description and track), not the track alone. */
    className?: string;
  }>;

/**
 * A slider with one thumb per value, an optional label and description above
 * the track, and the value shown at the end of the label line with
 * `showValue`. Arrows move by `step`, PageUp/PageDown by ten steps, Home and
 * End jump to `min` and `max`. Horizontal only. The root is a labelled,
 * described `group`; each thumb carries the description and the disabled
 * state too, since the thumbs are what assistive tech focuses.
 */
export function Slider({
  label,
  description,
  thumbLabels,
  formatValue = String,
  showValue = false,
  className,
  disabled,
  value,
  defaultValue,
  min = 0,
  onValueChange,
  "aria-label": ariaLabel,
  "aria-describedby": ariaDescribedBy,
  ...props
}: SliderProps): JSX.Element {
  const id = useId();
  const [internal, setInternal] = useState(defaultValue ?? [min]);
  const values = value ?? internal;
  const hasLabel = isPresent(label);
  const hasDescription = isPresent(description);
  const labelId = `${id}-label`;
  const descriptionId = hasDescription ? `${id}-description` : undefined;
  const describedBy =
    [ariaDescribedBy, descriptionId].filter(Boolean).join(" ") || undefined;
  // A single thumb is named by the slider's own name; a range's thumbs keep
  // Radix's "Minimum"/"Maximum" unless `thumbLabels` names them.
  const single = values.length === 1;
  const singleName = single
    ? ((hasLabel && typeof label === "string" ? label : undefined) ?? ariaLabel)
    : undefined;
  return (
    <div data-slot="slider-field" className={cn("ui:grid ui:gap-2", className)}>
      {hasLabel || hasDescription || showValue ? (
        <div className="ui:grid ui:gap-0.5">
          {hasLabel || showValue ? (
            <div className="ui:flex ui:items-baseline ui:justify-between ui:gap-2">
              {hasLabel ? (
                <span
                  id={labelId}
                  data-disabled={disabled ? "" : undefined}
                  className={CONTROL_LABEL_CLASS}
                >
                  {label}
                </span>
              ) : null}
              {showValue ? (
                <span className="ui:text-caption ui:text-muted-foreground ui:tabular-nums">
                  {values.map((v) => formatValue(v)).join(" – ")}
                </span>
              ) : null}
            </div>
          ) : null}
          {hasDescription ? (
            <p id={descriptionId} className={CONTROL_DESCRIPTION_CLASS}>
              {description}
            </p>
          ) : null}
        </div>
      ) : null}
      <SliderPrimitive.Root
        data-slot="slider"
        role="group"
        disabled={disabled}
        value={value}
        defaultValue={defaultValue}
        min={min}
        onValueChange={(next) => {
          setInternal(next);
          onValueChange?.(next);
        }}
        aria-label={ariaLabel}
        aria-labelledby={hasLabel ? labelId : undefined}
        aria-describedby={describedBy}
        className="ui:relative ui:flex ui:w-full ui:touch-none ui:select-none ui:items-center ui:data-disabled:pointer-events-none ui:data-disabled:opacity-50"
        {...props}
      >
        <SliderPrimitive.Track
          data-slot="slider-track"
          className="ui:relative ui:h-1.5 ui:w-full ui:grow ui:overflow-hidden ui:rounded-full ui:bg-muted"
        >
          <SliderPrimitive.Range
            data-slot="slider-range"
            className="ui:absolute ui:h-full ui:bg-primary"
          />
        </SliderPrimitive.Track>
        {values.map((thumbValue, i) => {
          const thumbName = thumbLabels?.[i] ?? singleName;
          return (
            <SliderPrimitive.Thumb
              // biome-ignore lint/suspicious/noArrayIndexKey: thumbs have no identity beyond their position
              key={i}
              data-slot="slider-thumb"
              // Spread only when defined: an explicit undefined would wipe
              // Radix's own range names.
              {...(thumbName ? { "aria-label": thumbName } : {})}
              aria-labelledby={
                thumbName === undefined && single && hasLabel
                  ? labelId
                  : undefined
              }
              aria-describedby={describedBy}
              aria-disabled={disabled || undefined}
              aria-valuetext={formatValue(thumbValue)}
              className="ui:block ui:size-4 ui:cursor-pointer ui:rounded-full ui:border ui:border-primary ui:bg-background ui:shadow-sm ui:focus-visible:focus-ring"
            />
          );
        })}
      </SliderPrimitive.Root>
    </div>
  );
}
