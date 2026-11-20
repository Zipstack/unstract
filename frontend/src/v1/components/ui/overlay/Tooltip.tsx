import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { Tooltip as RadixTooltip } from "radix-ui";
import type { JSX, ReactElement } from "react";

// Short text label; opens after a delay on hover and at once on keyboard focus.

export const TOOLTIP_DELAY_MS = 500;

const TOOLTIP_SURFACE =
  "ui:z-50 ui:max-w-xs ui:rounded-md ui:bg-foreground ui:px-2 ui:py-1 ui:font-sans ui:text-caption ui:text-background";

export type TooltipProps = Readonly<{
  /** Plain text only, so a tooltip never holds anything interactive. */
  content: string;
  /** The trigger, used as is (`asChild`): a focusable v1 control. */
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  /** Show it now, as the gallery does. */
  defaultOpen?: boolean;
  className?: string;
}>;

/** Wraps its own Radix provider, so no app-level setup is needed. */
export function Tooltip({
  content,
  children,
  side = "top",
  align = "center",
  defaultOpen,
  className,
}: TooltipProps): JSX.Element {
  return (
    <RadixTooltip.Provider delayDuration={TOOLTIP_DELAY_MS}>
      <RadixTooltip.Root defaultOpen={defaultOpen}>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal container={getPortalContainer()}>
          <RadixTooltip.Content
            data-slot="tooltip"
            side={side}
            align={align}
            sideOffset={4}
            collisionPadding={8}
            className={cn(TOOLTIP_SURFACE, className)}
          >
            {content}
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
