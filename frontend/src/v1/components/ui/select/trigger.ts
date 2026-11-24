/*
 * Classes shared by the selection triggers (Select, Combobox, MultiSelect) and
 * their popover lists. The trigger frames themselves come from the form's
 * `fieldFrameVariants`: `focus: "self"` for Select's button, `focus: "within"`
 * for the Combobox and MultiSelect frames around their input.
 */

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

/**
 * Widens a 16px button's hit area to 24px without changing its drawn size:
 * an `after` box 4px past each edge, part of the button, so it takes the
 * clicks (the Combobox Clear and Chip remove buttons).
 */
export const HIT_AREA_24 = "ui:relative ui:after:absolute ui:after:-inset-1";
