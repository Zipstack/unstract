import { cn } from "@v1/lib/cn";
import { ACTION_ICONS, STATUS_ICONS } from "@v1/lib/icons";
import type { LucideIcon } from "lucide-react";
import type { JSX, ReactNode } from "react";

/*
 * Pieces every menu shares: the surface, the row and what goes in a row.
 * Rows follow the drawn menus (frames 621:1114, 1084:630, 780:3510): 32 tall,
 * radius 6, a 16px icon 10 from the label, 13px medium text, and the
 * destructive row in the destructive colour.
 *
 * Icons and slots sit in `div`s, never `span`s: v0 forces an `svg.lucide`
 * under a `span` to 1em (see the v1 README).
 */

/**
 * The popover surface of every menu: the popover colour, radius 10,
 * `shadow-md`, at least 192 wide. Each content part caps its height at the
 * room Radix finds around the trigger, so a long menu scrolls instead of
 * running off-screen.
 */
export const MENU_SURFACE =
  "ui:z-50 ui:min-w-48 ui:overflow-x-hidden ui:overflow-y-auto ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:p-1.5 ui:text-popover-foreground ui:shadow-md ui:outline-none";

/**
 * A row. The highlighted row (pointer or keyboard) takes the accent; a
 * keyboard-focused row also shows the focus ring. A loading row is disabled
 * but keeps full opacity, so its spinner reads as work, not as unavailable.
 */
export const MENU_ITEM =
  "ui:relative ui:flex ui:min-h-8 ui:w-full ui:cursor-pointer ui:items-center ui:gap-2.5 ui:rounded-md ui:px-2 ui:py-1.5 ui:text-left ui:font-sans ui:text-body-small ui:font-medium ui:text-foreground ui:outline-none ui:select-none ui:focus-visible:focus-ring ui:data-highlighted:bg-accent ui:data-disabled:cursor-not-allowed ui:data-disabled:not-aria-busy:opacity-50 ui:aria-busy:cursor-progress";

/** Added to a destructive row: the destructive colour, label and icon alike. */
export const MENU_ITEM_DESTRUCTIVE =
  "ui:text-destructive ui:data-highlighted:bg-destructive/10";

/** A group label: overline type, not focusable. */
export const MENU_LABEL =
  "ui:px-2 ui:pt-2 ui:pb-1 ui:font-sans ui:text-overline ui:tracking-wide ui:text-muted-foreground ui:uppercase";

/** The rule between groups. */
export const MENU_SEPARATOR = "ui:-mx-1.5 ui:my-1.5 ui:h-px ui:bg-border";

const LoadingIcon = STATUS_ICONS.loading;
const SubmenuIcon = ACTION_ICONS.next;
const CheckIcon = ACTION_ICONS.confirm;

/** What a row can show besides its label. Every menu item takes these. */
export type MenuItemOptions = Readonly<{
  /** A 16px lucide glyph before the label, e.g. `ACTION_ICONS.edit`. */
  icon?: LucideIcon;
  /**
   * A shortcut hint shown at the end, e.g. "⌘D". It is only a hint: it is
   * hidden from screen readers, so bind the key yourself and pass
   * `aria-keyshortcuts` (e.g. "Meta+D") if the menu should announce it.
   */
  shortcut?: string;
  /** A second line in the caption role, read as the item's description. */
  description?: string;
  /** Styles the row apart. Put destructive rows last, after a separator. */
  destructive?: boolean;
  /**
   * Shows a spinner in place of the icon and disables the row, with
   * `aria-busy`. To keep the menu open while the work runs, call
   * `event.preventDefault()` in `onSelect`.
   */
  loading?: boolean;
}>;

/** The row classes for one item's options. */
export function menuItemClass(
  { destructive }: Pick<MenuItemOptions, "destructive">,
  className?: string,
): string {
  return cn(MENU_ITEM, destructive && MENU_ITEM_DESTRUCTIVE, className);
}

type MenuItemBodyProps = MenuItemOptions &
  Readonly<{
    children: ReactNode;
    /**
     * The row's id base. With a description, the label gets `${id}-label` and
     * the description `${id}-description`, for the row's `aria-labelledby`
     * and `aria-describedby` (see `describedRowProps`), so the description is
     * not read as part of the name.
     */
    rowId?: string;
    /** Something at the end instead of the shortcut (the submenu chevron). */
    trailing?: ReactNode;
    /** A slot before the label even without an icon (check and radio rows). */
    indicator?: ReactNode;
  }>;

/** The inside of a row: indicator, icon or spinner, label, description, hint. */
export function MenuItemBody({
  icon: Icon,
  shortcut,
  description,
  destructive,
  loading,
  children,
  rowId,
  trailing,
  indicator,
}: MenuItemBodyProps): JSX.Element {
  const glyph = loading ? (
    <LoadingIcon
      aria-hidden
      className="ui:size-4 ui:motion-safe:animate-spin"
    />
  ) : (
    Icon && <Icon aria-hidden className="ui:size-4" />
  );
  return (
    <>
      {indicator}
      {glyph && (
        <div
          data-slot="menu-item-icon"
          className={cn(
            "ui:flex ui:size-4 ui:shrink-0 ui:items-center ui:justify-center",
            !destructive && "ui:text-muted-foreground",
          )}
        >
          {glyph}
        </div>
      )}
      <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col">
        <div
          id={description && rowId ? `${rowId}-label` : undefined}
          className="ui:truncate"
        >
          {children}
        </div>
        {description && (
          <div
            id={rowId && `${rowId}-description`}
            className="ui:truncate ui:text-caption ui:font-normal ui:text-muted-foreground"
          >
            {description}
          </div>
        )}
      </div>
      {trailing ??
        (shortcut && (
          <kbd
            aria-hidden
            className="ui:ms-auto ui:shrink-0 ui:ps-4 ui:font-sans ui:text-caption ui:tracking-wide ui:text-muted-foreground"
          >
            {shortcut}
          </kbd>
        ))}
    </>
  );
}

/** The ARIA props naming a row by its label and describing it by its description. */
export function describedRowProps(
  rowId: string,
  description: string | undefined,
): { "aria-labelledby"?: string; "aria-describedby"?: string } {
  return description
    ? {
        "aria-labelledby": `${rowId}-label`,
        "aria-describedby": `${rowId}-description`,
      }
    : {};
}

/** The chevron at the end of a submenu trigger. */
export function SubmenuChevron(): JSX.Element {
  return (
    <div className="ui:ms-auto ui:flex ui:shrink-0 ui:text-muted-foreground">
      <SubmenuIcon aria-hidden className="ui:size-4" />
    </div>
  );
}

/** The check of a checked checkbox or radio row. */
export function MenuCheck(): JSX.Element {
  return <CheckIcon aria-hidden className="ui:size-4 ui:text-primary" />;
}

/** The fixed 16px slot the check sits in, so rows line up checked or not. */
export const MENU_INDICATOR_SLOT =
  "ui:flex ui:size-4 ui:shrink-0 ui:items-center ui:justify-center";
