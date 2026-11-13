import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { LucideIcon } from "lucide-react";
import type { ComponentProps, JSX } from "react";

/*
 * TEMPORARY SEAM. The v1 Button (P1-T02, UN-4272) is not built yet, so menus
 * open from these two plain buttons. When the Button lands, these become thin
 * wrappers over it (outline and ghost icon variants) and callers do not
 * change. Do not grow them into a second button system.
 *
 * Both take `ref` and spread props (React 19), so Radix's `asChild` triggers
 * can use them.
 */

const BASE =
  "ui:inline-flex ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:gap-2 ui:rounded-md ui:font-sans ui:text-body-small ui:font-medium ui:outline-none ui:focus-visible:focus-ring ui:disabled:cursor-not-allowed ui:disabled:opacity-50";

const ExpandIcon = ACTION_ICONS.expand;

export type MenuButtonProps = ComponentProps<"button">;

/** An outline button with a label and a chevron, e.g. "Sort by ⌄". */
export function MenuButton({
  className,
  children,
  type = "button",
  ...props
}: MenuButtonProps): JSX.Element {
  return (
    <button
      type={type}
      data-slot="menu-button"
      className={cn(
        BASE,
        "ui:group ui:h-8 ui:border ui:border-border ui:bg-card ui:px-3 ui:text-foreground ui:not-disabled:hover:bg-accent ui:data-[state=open]:bg-accent",
        className,
      )}
      {...props}
    >
      {children}
      <div className="ui:flex ui:text-muted-foreground">
        <ExpandIcon
          aria-hidden
          className="ui:size-4 ui:transition-transform ui:motion-reduce:transition-none ui:group-data-[state=open]:rotate-180"
        />
      </div>
    </button>
  );
}

export type MenuIconButtonProps = Omit<ComponentProps<"button">, "children"> &
  Readonly<{
    /** Required: the button has no text, so this is its only name. */
    "aria-label": string;
    /** Defaults to the kebab (`ACTION_ICONS.more`). */
    icon?: LucideIcon;
  }>;

/** A 32px ghost icon button: the row kebab of frames 621:1114 and 1084:630. */
export function MenuIconButton({
  className,
  icon: Icon = ACTION_ICONS.more,
  type = "button",
  ...props
}: MenuIconButtonProps): JSX.Element {
  return (
    <button
      type={type}
      data-slot="menu-icon-button"
      className={cn(
        BASE,
        "ui:size-8 ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:not-disabled:hover:bg-accent ui:not-disabled:hover:text-foreground ui:data-[state=open]:bg-accent ui:data-[state=open]:text-foreground",
        className,
      )}
      {...props}
    >
      <Icon aria-hidden className="ui:size-4" />
    </button>
  );
}
