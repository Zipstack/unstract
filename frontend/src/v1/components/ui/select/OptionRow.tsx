import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { JSX } from "react";
import type { SelectOption } from "./options";

const CheckIcon = ACTION_ICONS.confirm;

export type OptionRowProps = Readonly<{
  option: SelectOption;
  selected: boolean;
  /** The keyboard-active row, the target of `aria-activedescendant`. */
  active: boolean;
  id: string;
  onSelect?: () => void;
  onActivate?: () => void;
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
      data-active={active ? "" : undefined}
      data-slot="option"
      onMouseDown={(event) => event.preventDefault()}
      onClick={onSelect}
      onMouseMove={onActivate}
      className={cn(
        "ui:flex ui:w-full ui:cursor-pointer ui:items-center ui:gap-2.5 ui:rounded-md ui:px-2 ui:text-left ui:outline-none ui:select-none ui:data-active:bg-accent ui:data-highlighted:bg-accent",
        option.description ? "ui:h-12" : "ui:h-8",
        option.disabled && "ui:pointer-events-none ui:opacity-50",
        className,
      )}
    >
      {option.leading ? (
        <span
          data-slot="option-leading"
          className="ui:flex ui:size-4 ui:shrink-0 ui:items-center ui:justify-center ui:text-muted-foreground ui:[&>svg]:size-4"
        >
          {option.leading}
        </span>
      ) : null}
      <span className="ui:flex ui:min-w-0 ui:flex-col">
        <span className="ui:truncate ui:text-body-small ui:font-medium ui:text-foreground">
          {option.label}
        </span>
        {option.description ? (
          <span className="ui:truncate ui:text-caption ui:text-muted-foreground">
            {option.description}
          </span>
        ) : null}
      </span>
      {selected ? (
        <CheckIcon
          aria-hidden
          className="ui:ml-auto ui:size-4 ui:shrink-0 ui:text-primary"
        />
      ) : null}
    </div>
  );
}
