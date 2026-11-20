import { IconButton } from "@v1/components/ui/button";
import { isEscapeClearTarget } from "@v1/components/ui/form";
import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { Dialog as RadixDialog } from "radix-ui";
import {
  type ComponentProps,
  type JSX,
  type ReactNode,
  useCallback,
  useLayoutEffect,
  useRef,
} from "react";

// Parts every v1 overlay shares: the drawer here, the dialogs (P1-T07) too.

/** The dim layer behind a drawer or dialog: the whole viewport, under the panel. */
export const OVERLAY_SCRIM = "ui:fixed ui:inset-0 ui:z-50 ui:bg-scrim";

export type OverlayHeaderProps = Readonly<{
  title: ReactNode;
  description?: ReactNode;
  /** A logo or icon before the title. */
  leading?: ReactNode;
  /** A status chip after the title. */
  badge?: ReactNode;
  /** Disables the close button while the overlay's work runs. */
  busy?: boolean;
  className?: string;
}>;

/**
 * The header of a Radix Dialog (drawer or dialog): title, description and a
 * close button named "Close". Without a description, pass
 * `aria-describedby={undefined}` to the Content.
 */
export function OverlayHeader({
  title,
  description,
  leading,
  badge,
  busy,
  className,
}: OverlayHeaderProps): JSX.Element {
  return (
    <div
      data-slot="overlay-header"
      className={cn(
        "ui:flex ui:shrink-0 ui:items-start ui:gap-3 ui:border-b ui:border-border ui:px-6 ui:py-5",
        className,
      )}
    >
      {leading ? <div className="ui:flex ui:shrink-0">{leading}</div> : null}
      <HeaderText title={title} description={description} badge={badge} />
      <RadixDialog.Close asChild>
        <IconButton
          aria-label="Close"
          icon={ACTION_ICONS.close}
          disabled={busy}
          className="ui:-mt-1 ui:-mr-2"
        />
      </RadixDialog.Close>
    </div>
  );
}

function HeaderText({
  title,
  description,
  badge,
}: Pick<OverlayHeaderProps, "title" | "description" | "badge">) {
  return (
    <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-1">
      <div className="ui:flex ui:flex-wrap ui:items-center ui:gap-x-2 ui:gap-y-1">
        <RadixDialog.Title className="ui:m-0 ui:min-w-0 ui:break-words ui:text-page-title ui:text-foreground">
          {title}
        </RadixDialog.Title>
        {badge}
      </div>
      {description ? (
        <RadixDialog.Description className="ui:m-0 ui:text-body ui:text-muted-foreground">
          {description}
        </RadixDialog.Description>
      ) : null}
    </div>
  );
}

export type OverlayFooterProps = ComponentProps<"div"> &
  Readonly<{
    /** `end` (default) for a dialog; a drawer's actions start at the left. */
    align?: "start" | "end";
  }>;

/** The action bar at the bottom of a drawer or dialog. */
export function OverlayFooter({
  align = "end",
  className,
  ...props
}: OverlayFooterProps): JSX.Element {
  return (
    <div
      data-slot="overlay-footer"
      {...props}
      className={cn(
        "ui:flex ui:shrink-0 ui:flex-wrap ui:items-center ui:gap-3 ui:border-t ui:border-border ui:px-6 ui:py-4",
        align === "end" && "ui:justify-end",
        className,
      )}
    />
  );
}

/** The dismiss handlers of a Radix Dialog or Popover Content. */
export type DismissHandlers = Pick<
  ComponentProps<typeof RadixDialog.Content>,
  "onEscapeKeyDown" | "onInteractOutside"
>;

function isOnToast(target: EventTarget | null): boolean {
  return (
    target instanceof Element && target.closest("[data-slot=toast]") !== null
  );
}

/**
 * The Escape and outside-click rules every overlay shares; spread the result
 * onto the Radix Content. Escape first clears a filled SearchField, and a
 * click on a toast never closes the overlay. While `busy`, neither closes it.
 * `own` handlers run first and may prevent the close themselves.
 */
export function dismissGuards(
  busy = false,
  own: DismissHandlers = {},
): DismissHandlers {
  return {
    onEscapeKeyDown: (event) => {
      own.onEscapeKeyDown?.(event);
      if (busy || isEscapeClearTarget(event)) {
        event.preventDefault();
      }
    },
    onInteractOutside: (event) => {
      own.onInteractOutside?.(event);
      if (busy || isOnToast(event.target)) {
        event.preventDefault();
      }
    },
  };
}

type Opener = Readonly<{ element: HTMLElement; menuTriggerId: string | null }>;

function openerOf(doc: Document): Opener | null {
  const active = doc.activeElement;
  if (!(active instanceof HTMLElement) || active === doc.body) {
    return null;
  }
  // A Radix menu names itself after its trigger.
  const menu = active.closest("[role=menu]");
  return {
    element: active,
    menuTriggerId: menu?.getAttribute("aria-labelledby") ?? null,
  };
}

function returnTarget(opener: Opener | null): HTMLElement | null {
  if (!opener) {
    return null;
  }
  if (opener.element.isConnected) {
    return opener.element;
  }
  const { menuTriggerId } = opener;
  return menuTriggerId
    ? opener.element.ownerDocument.getElementById(menuTriggerId)
    : null;
}

/**
 * Remembers what had focus when `open` turned true. Pass the result as the
 * Content's `onCloseAutoFocus`: focus goes back there, or, when that was a
 * menu item that has since closed, to the menu's trigger. With neither, Radix
 * falls back to its own trigger.
 */
export function useReturnFocus(open: boolean): (event: Event) => void {
  const opener = useRef<Opener | null>(null);
  // A layout effect runs before a menu that opened the overlay unmounts.
  useLayoutEffect(() => {
    if (open) {
      opener.current = openerOf(document);
    }
  }, [open]);
  return useCallback((event: Event) => {
    const target = returnTarget(opener.current);
    opener.current = null;
    if (target) {
      event.preventDefault();
      target.focus();
    }
  }, []);
}
