import {
  Button,
  type ButtonProps,
  IconButton,
  type IconButtonProps,
} from "@v1/components/ui/button";
import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import type { LucideIcon } from "lucide-react";
import type { JSX } from "react";

// Thin wrappers over Button and IconButton; both take ref and props, so `asChild` triggers can use them.

const ExpandIcon = ACTION_ICONS.expand;

// Omit per union member, so a wrapper keeps "needs a name".
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown
  ? Omit<T, K>
  : never;

export type MenuButtonProps = Omit<ButtonProps, "variant" | "trailingIcon">;

/** An outline button with a label and a chevron, e.g. "Sort by ⌄". */
export function MenuButton({
  className,
  children,
  ...props
}: MenuButtonProps): JSX.Element {
  return (
    <Button
      variant="outline"
      data-slot="menu-button"
      className={cn("ui:group ui:data-[state=open]:bg-accent", className)}
      {...props}
    >
      {children}
      <div className="ui:flex ui:text-muted-foreground">
        <ExpandIcon
          aria-hidden
          className="ui:size-4 ui:transition-transform ui:motion-reduce:transition-none ui:group-data-[state=open]:rotate-180"
        />
      </div>
    </Button>
  );
}

export type MenuIconButtonProps = DistributiveOmit<
  IconButtonProps,
  "icon" | "variant"
> &
  Readonly<{
    /** Defaults to the kebab (`ACTION_ICONS.more`). */
    icon?: LucideIcon;
  }>;

/** A 32px ghost icon button: the row kebab of frames 621:1114 and 1084:630. */
export function MenuIconButton({
  className,
  icon = ACTION_ICONS.more,
  ...props
}: MenuIconButtonProps): JSX.Element {
  return (
    <IconButton
      variant="ghost"
      icon={icon}
      data-slot="menu-icon-button"
      className={cn(
        "ui:data-[state=open]:bg-accent ui:data-[state=open]:text-foreground",
        className,
      )}
      {...props}
    />
  );
}
