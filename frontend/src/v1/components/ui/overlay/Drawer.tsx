import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { Dialog as RadixDialog } from "radix-ui";
import type { ComponentProps, JSX, ReactElement, ReactNode } from "react";
import {
  dismissGuards,
  OVERLAY_SCRIM,
  OverlayFooter,
  OverlayHeader,
  useReturnFocus,
} from "./parts";

// Right-hand detail panel (A05, L07, L08, C05); no Dialog.Overlay, so page scroll is not locked.

const SIZE = { md: "ui:w-120", lg: "ui:w-160" } as const;

const DRAWER_BODY =
  "ui:flex ui:min-h-0 ui:flex-1 ui:flex-col ui:overflow-y-auto ui:px-6 ui:py-5";

const DRAWER_SURFACE =
  "ui:fixed ui:inset-y-0 ui:right-0 ui:z-50 ui:flex ui:max-w-full ui:flex-col ui:border-l ui:border-border ui:bg-card ui:text-card-foreground ui:shadow-xl ui:outline-none";

type PanelProps = Readonly<{
  title: string;
  description?: ReactNode;
  /** A logo or icon before the title (C05). */
  leading?: ReactNode;
  /** A status chip after the title. */
  badge?: ReactNode;
  /** `md` 480 (default) or `lg` 640 wide, never wider than the screen. */
  size?: keyof typeof SIZE;
  /** Buttons for the bar at the bottom, primary first. */
  actions?: ReactNode;
  /** While true, Escape, a click outside and the close button do nothing. */
  busy?: boolean;
  /** The sections, a skeleton while loading, or an InlineAlert on error. */
  children: ReactNode;
  className?: string;
}>;

export type DrawerProps = PanelProps &
  Readonly<{
    open?: boolean;
    defaultOpen?: boolean;
    onOpenChange?: (open: boolean) => void;
    /** The opener, used as the trigger itself (`asChild`); omit it when `open` is driven by a row or menu. */
    trigger?: ReactElement;
  }>;

/** A right-hand drawer with a header, scrolling sections and an action bar. */
export function Drawer({
  open,
  defaultOpen,
  onOpenChange,
  trigger,
  ...panel
}: DrawerProps): JSX.Element {
  // Uncontrolled, it opens from its trigger, where Radix returns focus.
  const onCloseAutoFocus = useReturnFocus(open === true);
  return (
    <RadixDialog.Root
      open={open}
      defaultOpen={defaultOpen}
      onOpenChange={onOpenChange}
    >
      {trigger ? (
        <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>
      ) : null}
      <RadixDialog.Portal container={getPortalContainer()}>
        <div data-slot="drawer-scrim" className={OVERLAY_SCRIM} />
        <DrawerPanel {...panel} onCloseAutoFocus={onCloseAutoFocus} />
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

function DrawerPanel({
  title,
  description,
  leading,
  badge,
  size = "md",
  actions,
  busy,
  children,
  className,
  onCloseAutoFocus,
}: PanelProps & Readonly<{ onCloseAutoFocus: (event: Event) => void }>) {
  return (
    <RadixDialog.Content
      data-slot="drawer"
      {...(description ? {} : { "aria-describedby": undefined })}
      {...dismissGuards(busy)}
      onCloseAutoFocus={onCloseAutoFocus}
      className={cn(DRAWER_SURFACE, SIZE[size], className)}
    >
      <OverlayHeader {...{ title, description, leading, badge, busy }} />
      <div data-slot="drawer-body" className={DRAWER_BODY}>
        {children}
      </div>
      {actions ? <OverlayFooter align="start">{actions}</OverlayFooter> : null}
    </RadixDialog.Content>
  );
}

export type DrawerSectionProps = Omit<ComponentProps<"section">, "title"> &
  Readonly<{
    /** Shown small and upper-case above the content. */
    title?: string;
    /** A short note at the right of the title, e.g. "11 workflows". */
    meta?: ReactNode;
  }>;

/** One part of a drawer's body; a rule separates sections. */
export function DrawerSection({
  title,
  meta,
  className,
  children,
  ...props
}: DrawerSectionProps): JSX.Element {
  return (
    <section
      data-slot="drawer-section"
      {...props}
      className={cn(
        "ui:flex ui:flex-col ui:gap-3 ui:border-b ui:border-border ui:py-5 ui:first:pt-0 ui:last:border-b-0 ui:last:pb-0",
        className,
      )}
    >
      {title ? <SectionHeading title={title} meta={meta} /> : null}
      {children}
    </section>
  );
}

function SectionHeading({
  title,
  meta,
}: Readonly<{ title: string; meta?: ReactNode }>) {
  return (
    <div className="ui:flex ui:items-baseline ui:justify-between ui:gap-3">
      <h3 className="ui:m-0 ui:text-overline ui:tracking-wide ui:text-muted-foreground ui:uppercase">
        {title}
      </h3>
      {meta ? (
        <div className="ui:text-caption ui:text-muted-foreground">{meta}</div>
      ) : null}
    </div>
  );
}
