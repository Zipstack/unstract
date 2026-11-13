import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { JSX } from "react";
import type { SelectOption } from "./options";

const CheckIcon = ACTION_ICONS.confirm;

/*
 * The row's classes, shared with the Radix `Select.Item`, which renders its
 * own element. The row is `ui:h-8`, or `ui:h-12` with a description.
 */

/** The row frame; the active or highlighted row takes the accent. */
export const OPTION_ROW_CLASS =
  "ui:flex ui:w-full ui:cursor-pointer ui:items-center ui:gap-2.5 ui:rounded-md ui:px-2 ui:text-left ui:outline-none ui:select-none ui:data-active:bg-accent ui:data-highlighted:bg-accent";

/** The option's label. */
export const OPTION_LABEL_CLASS =
  "ui:truncate ui:text-body-small ui:font-medium ui:text-foreground";

/** The line under the label. */
export const OPTION_DESCRIPTION_CLASS =
  "ui:truncate ui:text-caption ui:text-muted-foreground";

/** The 16px slot for a lucide icon or a provider logo before the label. */
export const OPTION_LEADING_CLASS =
  "ui:flex ui:size-4 ui:shrink-0 ui:items-center ui:justify-center ui:text-muted-foreground ui:[&>svg]:size-4";

/** The check on the selected option. */
export const OPTION_CHECK_CLASS =
  "ui:ml-auto ui:size-4 ui:shrink-0 ui:text-primary";

export type OptionRowProps = Readonly<{
  option: SelectOption;
  selected: boolean;
  /** The keyboard-active row, the target of `aria-activedescendant`. */
  active: boolean;
  id: string;
  onSelect?: () => void;
  onActivate?: () => void;
  /** A virtual list's size and this row's 1-based place in it. */
  "aria-setsize"?: number;
  "aria-posinset"?: number;
  className?: string;
}>;

/**
 * One `role="option"` row in a combobox listbox. Focus stays on the
 * combobox input, so the row is not focusable and its mousedown is
 * default-prevented to keep the input from losing focus.
 */
export function OptionRow({
  option,
  selected,
  active,
  id,
  onSelect,
  onActivate,
  "aria-setsize": setSize,
  "aria-posinset": posInSet,
  className,
}: OptionRowProps): JSX.Element {
  return (
    // biome-ignore lint/a11y/useFocusableInteractive: focus stays on the combobox input, which points here with aria-activedescendant.
    // biome-ignore lint/a11y/useKeyWithClickEvents: the combobox input handles the keyboard for every row.
    <div
      role="option"
      id={id}
      aria-selected={selected}
      aria-disabled={option.disabled || undefined}
      aria-setsize={setSize}
      aria-posinset={posInSet}
      data-active={active ? "" : undefined}
      data-slot="option"
      onMouseDown={(event) => event.preventDefault()}
      onClick={option.disabled ? undefined : onSelect}
      onMouseMove={option.disabled ? undefined : onActivate}
      className={cn(
        OPTION_ROW_CLASS,
        option.description ? "ui:h-12" : "ui:h-8",
        option.disabled && "ui:pointer-events-none ui:opacity-50",
        className,
      )}
    >
      {option.leading ? (
        <span data-slot="option-leading" className={OPTION_LEADING_CLASS}>
          {option.leading}
        </span>
      ) : null}
      <span className="ui:flex ui:min-w-0 ui:flex-col">
        <span className={OPTION_LABEL_CLASS}>{option.label}</span>
        {option.description ? (
          <span className={OPTION_DESCRIPTION_CLASS}>{option.description}</span>
        ) : null}
      </span>
      {selected ? (
        <CheckIcon aria-hidden className={OPTION_CHECK_CLASS} />
      ) : null}
    </div>
  );
}
