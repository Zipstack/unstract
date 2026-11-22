import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { Popover as RadixPopover } from "radix-ui";
import { type ComponentProps, type JSX, type ReactNode, useId } from "react";
import { dismissGuards } from "./parts";

// Click-opened panel that may hold controls (C13); focus moves in but is not trapped.

/** The surface every popover and hover card shares. */
export const POPOVER_SURFACE =
  "ui:z-50 ui:w-72 ui:max-w-(--radix-popper-available-width) ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:p-4 ui:text-popover-foreground ui:shadow-lg ui:outline-none";

const POPOVER_CONTENT = cn(
  POPOVER_SURFACE,
  "ui:max-h-(--radix-popover-content-available-height) ui:overflow-y-auto",
);

export type PopoverProps = ComponentProps<typeof RadixPopover.Root>;

export function Popover(props: PopoverProps): JSX.Element {
  return <RadixPopover.Root {...props} />;
}

export type PopoverTriggerProps = ComponentProps<typeof RadixPopover.Trigger>;

/** The control that opens it. Pass `asChild` with a v1 `Button` or `IconButton`. */
export function PopoverTrigger(props: PopoverTriggerProps): JSX.Element {
  return <RadixPopover.Trigger data-slot="popover-trigger" {...props} />;
}

/** The popover is a dialog, so the types require a name. */
type PopoverName =
  | Readonly<{ title: string; "aria-label"?: never }>
  | Readonly<{ title?: never; "aria-label": string }>;

export type PopoverContentProps = Omit<
  ComponentProps<typeof RadixPopover.Content>,
  "title" | "aria-label" | "asChild" | "forceMount"
> &
  PopoverName &
  Readonly<{
    /** A line under the title. */
    description?: ReactNode;
    /** While true, Escape and a click outside do nothing; a trigger click still closes it. */
    busy?: boolean;
  }>;

/** The panel, portalled into the v1 portal container; it stays on screen. */
export function PopoverContent({
  title,
  description,
  busy,
  onEscapeKeyDown,
  onInteractOutside,
  className,
  children,
  ...props
}: PopoverContentProps): JSX.Element {
  const id = useId();
  return (
    <RadixPopover.Portal container={getPortalContainer()}>
      <RadixPopover.Content
        data-slot="popover"
        aria-labelledby={title ? `${id}-title` : undefined}
        aria-describedby={description ? `${id}-description` : undefined}
        sideOffset={4}
        collisionPadding={8}
        {...props}
        {...dismissGuards(busy, { onEscapeKeyDown, onInteractOutside })}
        className={cn(POPOVER_CONTENT, className)}
      >
        <PopoverHeading id={id} title={title} description={description} />
        {children}
      </RadixPopover.Content>
    </RadixPopover.Portal>
  );
}

function PopoverHeading({
  id,
  title,
  description,
}: Readonly<{ id: string; title?: string; description?: ReactNode }>) {
  if (!(title || description)) {
    return null;
  }
  return (
    <div className="ui:mb-3 ui:flex ui:flex-col ui:gap-0.5">
      {title ? (
        <h2
          id={`${id}-title`}
          className="ui:m-0 ui:text-body ui:font-semibold ui:text-popover-foreground"
        >
          {title}
        </h2>
      ) : null}
      {description ? (
        <p
          id={`${id}-description`}
          className="ui:m-0 ui:text-caption ui:text-muted-foreground"
        >
          {description}
        </p>
      ) : null}
    </div>
  );
}
