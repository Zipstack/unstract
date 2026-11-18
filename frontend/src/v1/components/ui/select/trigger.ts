/*
 * Classes shared by the selection triggers (Select, Combobox, MultiSelect) and
 * their popover lists.
 */

/** The 32-tall field frame, P1-T03's `FieldFrame` recipe verbatim. */
export const TRIGGER_FRAME =
  "ui:box-border ui:flex ui:h-8 ui:w-full ui:min-w-0 ui:items-center ui:gap-1.5 ui:rounded-md ui:border ui:border-input ui:bg-background ui:px-2.5 ui:text-body ui:text-foreground ui:transition-[border-color,box-shadow] ui:hover:border-muted-foreground ui:focus-visible:focus-ring ui:data-invalid:border-destructive ui:data-invalid:[--ring:var(--destructive)] ui:data-disabled:pointer-events-none ui:data-disabled:opacity-50 ui:disabled:pointer-events-none ui:disabled:opacity-50";

/** The placeholder text in a trigger. */
export const TRIGGER_PLACEHOLDER = "ui:text-muted-foreground";

/** The `ChevronDown` at the end of a trigger. */
export const TRIGGER_CHEVRON = "ui:size-4 ui:shrink-0 ui:text-muted-foreground";

/**
 * Every popover list. Each component adds its width from the Radix trigger
 * width variable.
 */
export const LIST_SURFACE =
  "ui:z-50 ui:min-w-48 ui:max-h-80 ui:overflow-auto ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:p-1.5 ui:text-body-small ui:shadow-md";
