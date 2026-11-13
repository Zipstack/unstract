import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import type { DropdownMenu as RadixDropdownMenu } from "radix-ui";
import { type ComponentProps, type JSX, type ReactNode, useId } from "react";
import {
  MENU_INDICATOR_SLOT,
  MENU_LABEL,
  MENU_SEPARATOR,
  MENU_SURFACE,
  describedRowProps,
  MenuCheck,
  MenuItemBody,
  type MenuItemOptions,
  menuItemClass,
  SubmenuChevron,
} from "./item";

/*
 * The parts DropdownMenu and ContextMenu share. Both Radix menus are built on
 * the same Menu primitive, so their item parts take the same props; each
 * family passes its own primitives here and gets styled parts back. Only the
 * root, trigger and content differ, and those live in each family's file.
 */

type P = typeof RadixDropdownMenu;

/** The Radix parts a menu family supplies. */
export type MenuPrimitives = Readonly<{
  Portal: P["Portal"];
  Item: P["Item"];
  CheckboxItem: P["CheckboxItem"];
  RadioGroup: P["RadioGroup"];
  RadioItem: P["RadioItem"];
  ItemIndicator: P["ItemIndicator"];
  Label: P["Label"];
  Separator: P["Separator"];
  Group: P["Group"];
  Sub: P["Sub"];
  SubTrigger: P["SubTrigger"];
  SubContent: P["SubContent"];
}>;

export type MenuItemProps = Omit<ComponentProps<P["Item"]>, "children"> &
  MenuItemOptions &
  Readonly<{ children: ReactNode }>;

export type MenuCheckboxItemProps = Omit<
  ComponentProps<P["CheckboxItem"]>,
  "children"
> &
  Omit<MenuItemOptions, "destructive"> &
  Readonly<{ children: ReactNode }>;

export type MenuRadioItemProps = Omit<
  ComponentProps<P["RadioItem"]>,
  "children"
> &
  Omit<MenuItemOptions, "destructive"> &
  Readonly<{ children: ReactNode }>;

export type MenuSubTriggerProps = Omit<
  ComponentProps<P["SubTrigger"]>,
  "children"
> &
  Pick<MenuItemOptions, "icon" | "description"> &
  Readonly<{ children: ReactNode }>;

/** Builds the styled item parts of one menu family. */
export function createMenuParts(R: MenuPrimitives, family: string) {
  function Item({
    icon,
    shortcut,
    description,
    destructive,
    loading,
    disabled,
    className,
    children,
    ...props
  }: MenuItemProps): JSX.Element {
    const rowId = useId();
    return (
      <R.Item
        data-slot={`${family}-item`}
        data-destructive={destructive || undefined}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...describedRowProps(rowId, description)}
        className={menuItemClass({ destructive }, className)}
        {...props}
      >
        <MenuItemBody
          icon={icon}
          shortcut={shortcut}
          description={description}
          destructive={destructive}
          loading={loading}
          rowId={rowId}
        >
          {children}
        </MenuItemBody>
      </R.Item>
    );
  }

  function Indicator(): JSX.Element {
    return (
      <div className={MENU_INDICATOR_SLOT}>
        <R.ItemIndicator asChild>
          <div className="ui:flex">
            <MenuCheck />
          </div>
        </R.ItemIndicator>
      </div>
    );
  }

  /** A row that toggles; `checked` and `onCheckedChange` are Radix's. */
  function CheckboxItem({
    icon,
    shortcut,
    description,
    loading,
    disabled,
    className,
    children,
    ...props
  }: MenuCheckboxItemProps): JSX.Element {
    const rowId = useId();
    return (
      <R.CheckboxItem
        data-slot={`${family}-checkbox-item`}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...describedRowProps(rowId, description)}
        className={menuItemClass({}, className)}
        {...props}
      >
        <MenuItemBody
          icon={icon}
          shortcut={shortcut}
          description={description}
          loading={loading}
          rowId={rowId}
          indicator={<Indicator />}
        >
          {children}
        </MenuItemBody>
      </R.CheckboxItem>
    );
  }

  /** One choice of a `RadioGroup` (the sort menu, frame 621:903). */
  function RadioItem({
    icon,
    shortcut,
    description,
    loading,
    disabled,
    className,
    children,
    ...props
  }: MenuRadioItemProps): JSX.Element {
    const rowId = useId();
    return (
      <R.RadioItem
        data-slot={`${family}-radio-item`}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...describedRowProps(rowId, description)}
        className={menuItemClass({}, className)}
        {...props}
      >
        <MenuItemBody
          icon={icon}
          shortcut={shortcut}
          description={description}
          loading={loading}
          rowId={rowId}
          indicator={<Indicator />}
        >
          {children}
        </MenuItemBody>
      </R.RadioItem>
    );
  }

  function RadioGroup(props: ComponentProps<P["RadioGroup"]>): JSX.Element {
    return <R.RadioGroup data-slot={`${family}-radio-group`} {...props} />;
  }

  /** A group label. Wrap it and its rows in a `Group` so the rows are named by it. */
  function Label({
    className,
    ...props
  }: ComponentProps<P["Label"]>): JSX.Element {
    return (
      <R.Label
        data-slot={`${family}-label`}
        className={cn(MENU_LABEL, className)}
        {...props}
      />
    );
  }

  function Separator({
    className,
    ...props
  }: ComponentProps<P["Separator"]>): JSX.Element {
    return (
      <R.Separator
        data-slot={`${family}-separator`}
        className={cn(MENU_SEPARATOR, className)}
        {...props}
      />
    );
  }

  function Group(props: ComponentProps<P["Group"]>): JSX.Element {
    return <R.Group data-slot={`${family}-group`} {...props} />;
  }

  /** A submenu: Right (or Enter) opens it, Left closes it. */
  function Sub(props: ComponentProps<P["Sub"]>): JSX.Element {
    return <R.Sub {...props} />;
  }

  function SubTrigger({
    icon,
    description,
    className,
    children,
    ...props
  }: MenuSubTriggerProps): JSX.Element {
    const rowId = useId();
    return (
      <R.SubTrigger
        data-slot={`${family}-sub-trigger`}
        {...describedRowProps(rowId, description)}
        className={menuItemClass(
          {},
          cn("ui:data-[state=open]:bg-accent", className),
        )}
        {...props}
      >
        <MenuItemBody
          icon={icon}
          description={description}
          rowId={rowId}
          trailing={<SubmenuChevron />}
        >
          {children}
        </MenuItemBody>
      </R.SubTrigger>
    );
  }

  /** A submenu's list. It flips to the other side when there is no room. */
  function SubContent({
    className,
    collisionPadding = 8,
    ...props
  }: ComponentProps<P["SubContent"]>): JSX.Element {
    return (
      <R.Portal container={getPortalContainer()}>
        <R.SubContent
          data-slot={`${family}-sub-content`}
          collisionPadding={collisionPadding}
          className={cn(MENU_SURFACE, className)}
          {...props}
        />
      </R.Portal>
    );
  }

  return {
    Item,
    CheckboxItem,
    RadioGroup,
    RadioItem,
    Label,
    Separator,
    Group,
    Sub,
    SubTrigger,
    SubContent,
  };
}
