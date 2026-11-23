import { IconButton } from "@v1/components/ui/button";
import { isEscapeClearTarget } from "@v1/components/ui/form";
import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { Dialog as RadixDialog } from "radix-ui";
import type { ComponentProps, JSX, ReactNode } from "react";

// Parts the drawer and dialogs share; the popover uses dismissGuards too.

/** The dim layer behind a drawer or dialog: the whole viewport, under the panel. */
export const OVERLAY_SCRIM = "ui:fixed ui:inset-0 ui:z-50 ui:bg-scrim";

const TITLE_SIZE = {
  page: "ui:text-page-title",
  section: "ui:text-section-title",
} as const;

export type OverlayHeaderProps = Readonly<{
  title: string;
  /** `page` 20 (default; drawers, form dialogs) or `section` 16 (confirm dialogs). */
  titleSize?: keyof typeof TITLE_SIZE;
  description?: ReactNode;
  /** A logo or icon before the title. */
  leading?: ReactNode;
  /** A status chip after the title. */
  badge?: ReactNode;
  /** Disables the close button while the overlay's work runs. */
  busy?: boolean;
  className?: string;
}>;

/** Title, description and a "Close" button inside a Radix Dialog; it throws inside an AlertDialog, so a confirm is a Dialog with role="alertdialog". */
export function OverlayHeader({
  leading,
  busy,
  className,
  ...text
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
      <HeaderText {...text} />
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
  titleSize = "page",
  description,
  badge,
}: Pick<OverlayHeaderProps, "title" | "titleSize" | "description" | "badge">) {
  return (
    <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-1">
      <div className="ui:flex ui:flex-wrap ui:items-center ui:gap-x-2 ui:gap-y-1">
        <RadixDialog.Title
          className={cn(
            "ui:m-0 ui:min-w-0 ui:break-words ui:text-foreground",
            TITLE_SIZE[titleSize],
          )}
        >
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

/** Shared Escape and outside-click rules, spread onto a Radix Content; `own` handlers run first. */
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
      if (busy) {
        event.preventDefault();
      }
    },
  };
}
