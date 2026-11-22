import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { HoverCard as RadixHoverCard } from "radix-ui";
import type { ComponentProps, JSX } from "react";
import { POPOVER_SURFACE } from "./Popover";

// Preview on hover or focus; it never takes focus, so it holds nothing a user must reach.

export type HoverCardProps = ComponentProps<typeof RadixHoverCard.Root>;

export function HoverCard({
  openDelay = 500,
  closeDelay = 300,
  ...props
}: HoverCardProps): JSX.Element {
  return (
    <RadixHoverCard.Root
      openDelay={openDelay}
      closeDelay={closeDelay}
      {...props}
    />
  );
}

export type HoverCardTriggerProps = ComponentProps<
  typeof RadixHoverCard.Trigger
>;

/** What it previews. Pass `asChild` with a focusable element, such as a v1 `Link`. */
export function HoverCardTrigger(props: HoverCardTriggerProps): JSX.Element {
  return <RadixHoverCard.Trigger data-slot="hover-card-trigger" {...props} />;
}

export type HoverCardContentProps = Omit<
  ComponentProps<typeof RadixHoverCard.Content>,
  "asChild" | "forceMount"
>;

/** The card, portalled into the v1 portal container; it stays on screen. */
export function HoverCardContent({
  sideOffset = 4,
  collisionPadding = 8,
  className,
  ...props
}: HoverCardContentProps): JSX.Element {
  return (
    <RadixHoverCard.Portal container={getPortalContainer()}>
      <RadixHoverCard.Content
        data-slot="hover-card"
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn(POPOVER_SURFACE, className)}
        {...props}
      />
    </RadixHoverCard.Portal>
  );
}
