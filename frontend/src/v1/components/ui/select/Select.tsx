import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { getPortalContainer } from "@v1/lib/portal";
import { Select as SelectPrimitive } from "radix-ui";
import type { JSX } from "react";
import {
  OPTION_CHECK_CLASS,
  OPTION_DESCRIPTION_CLASS,
  OPTION_LABEL_CLASS,
  OPTION_LEADING_CLASS,
  OPTION_ROW_CLASS,
} from "./OptionRow";
import type { SelectOption } from "./options";
import {
  LIST_SURFACE,
  TRIGGER_CHEVRON,
  TRIGGER_FRAME,
  TRIGGER_PLACEHOLDER,
} from "./trigger";

const ChevronIcon = ACTION_ICONS.expand;
const CheckIcon = ACTION_ICONS.confirm;

export type SelectProps = Readonly<{
  options: readonly SelectOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  name?: string;
  required?: boolean;
  disabled?: boolean;
  invalid?: boolean;
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
  /** Classes for the trigger. */
  className?: string;
}>;

/**
 * A single choice from a short list (under about 50 options; longer lists
 * use `Combobox`), on Radix Select: every option is rendered, and Radix
 * handles the keyboard (arrows, Home, End, type-ahead on the label, Enter,
 * Escape). A `value` or `defaultValue` that matches no option shows the placeholder.
 */
export function Select({
  options,
  value,
  defaultValue,
  onValueChange,
  placeholder,
  name,
  required,
  disabled,
  invalid,
  id,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
  "aria-describedby": ariaDescribedBy,
  className,
}: SelectProps): JSX.Element {
  // Radix leaves the trigger blank for a value no item has; "" (Radix's
  // empty value) shows the placeholder instead.
  const known = (candidate: string) =>
    options.some((option) => option.value === candidate);
  return (
    <SelectPrimitive.Root
      value={value === undefined || known(value) ? value : ""}
      defaultValue={
        defaultValue === undefined || known(defaultValue)
          ? defaultValue
          : undefined
      }
      onValueChange={onValueChange}
      name={name}
      required={required}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        id={id}
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        aria-describedby={ariaDescribedBy}
        aria-invalid={invalid || undefined}
        data-invalid={invalid ? "" : undefined}
        data-slot="select-trigger"
        className={cn(TRIGGER_FRAME, "ui:cursor-pointer", className)}
      >
        {/*
         * The selected option's leading and label render here (its ItemText).
         * Radix drops SelectValue's className, so this wrapper lays out the
         * value element with child variants: one row that truncates and
         * leaves the chevron in the trigger.
         */}
        <span
          data-slot="select-value"
          className="ui:flex ui:min-w-0 ui:flex-1 ui:items-center ui:*:flex ui:*:min-w-0 ui:*:flex-1 ui:*:items-center ui:*:gap-1.5 ui:*:truncate"
        >
          <SelectPrimitive.Value
            data-slot="select-value-text"
            placeholder={
              <span className={TRIGGER_PLACEHOLDER}>{placeholder}</span>
            }
          />
        </span>
        <SelectPrimitive.Icon asChild>
          <ChevronIcon aria-hidden className={TRIGGER_CHEVRON} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal container={getPortalContainer()}>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className={cn(
            LIST_SURFACE,
            "ui:flex ui:flex-col ui:overflow-hidden ui:w-(--radix-select-trigger-width)",
          )}
        >
          <SelectPrimitive.Viewport className="ui:flex ui:min-h-0 ui:flex-col ui:gap-0.5 ui:max-h-(--radix-select-content-available-height)">
            {/*
             * Radix's Content is the listbox, which must hold at least one
             * option and nothing but options and groups (axe flags a status
             * element, even inside a group, and an empty listbox), so the
             * empty row is a disabled option outside Radix's collection: the
             * keyboard never lands on it and it cannot be chosen.
             */}
            {options.length === 0 ? (
              // biome-ignore lint/a11y/useFocusableInteractive: focus stays on Radix's listbox; this disabled row is never a target.
              <div
                role="option"
                aria-selected={false}
                aria-disabled
                data-slot="option-empty"
                className="ui:flex ui:h-8 ui:items-center ui:px-2 ui:text-caption ui:text-muted-foreground"
              >
                No options
              </div>
            ) : null}
            {options.map((option) => (
              <SelectItem key={option.value} option={option} />
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

/**
 * One option. The leading and label sit in `ItemText`, which Radix copies
 * into the trigger; the description stays outside it so the trigger never
 * shows it, indented past the leading slot to line up with the label.
 */
function SelectItem({
  option,
}: Readonly<{ option: SelectOption }>): JSX.Element {
  return (
    <SelectPrimitive.Item
      value={option.value}
      textValue={option.label}
      disabled={option.disabled}
      data-slot="option"
      className={cn(
        OPTION_ROW_CLASS,
        "ui:data-disabled:pointer-events-none ui:data-disabled:opacity-50",
        option.description ? "ui:h-12" : "ui:h-8",
      )}
    >
      <span className="ui:flex ui:min-w-0 ui:flex-col">
        {/* Radix drops ItemText's className, so its parent lays it out. */}
        <span
          className={cn(
            OPTION_LABEL_CLASS,
            "ui:*:flex ui:*:min-w-0 ui:*:items-center ui:*:gap-2.5",
          )}
        >
          <SelectPrimitive.ItemText>
            {option.leading ? (
              <span data-slot="option-leading" className={OPTION_LEADING_CLASS}>
                {option.leading}
              </span>
            ) : null}
            <span className="ui:min-w-0 ui:truncate">{option.label}</span>
          </SelectPrimitive.ItemText>
        </span>
        {option.description ? (
          <span
            className={cn(
              OPTION_DESCRIPTION_CLASS,
              option.leading && "ui:pl-6.5",
            )}
          >
            {option.description}
          </span>
        ) : null}
      </span>
      <SelectPrimitive.ItemIndicator asChild>
        <CheckIcon aria-hidden className={OPTION_CHECK_CLASS} />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}
