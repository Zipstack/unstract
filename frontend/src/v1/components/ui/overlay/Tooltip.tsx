import { getPortalContainer } from "@v1/lib/portal";
import { Tooltip as RadixTooltip } from "radix-ui";
import type { ComponentProps, JSX, ReactElement } from "react";

// Short text label; opens after a delay on hover and at once on keyboard focus.

export const TOOLTIP_DELAY_MS = 500;

const TOOLTIP_SURFACE =
  "ui:z-50 ui:max-w-xs ui:rounded-md ui:bg-foreground ui:px-2 ui:py-1 ui:font-sans ui:text-caption ui:text-background";

export type TooltipProps = Omit<
  ComponentProps<typeof RadixTooltip.Trigger>,
  "asChild" | "children" | "content"
> &
  Readonly<{
    /** Plain text only, so a tooltip never holds anything interactive. */
    content: string;
    /** The trigger, used as is (`asChild`): a focusable v1 control. */
    children: ReactElement;
    side?: "top" | "right" | "bottom" | "left";
    align?: "start" | "center" | "end";
    /** Show it now, as the gallery does. */
    defaultOpen?: boolean;
  }>;

/** Wraps its own Radix provider; other props (a parent `asChild`'s too) reach the trigger. */
export function Tooltip({
  content,
  children,
  side = "top",
  align = "center",
  defaultOpen,
  ...trigger
}: TooltipProps): JSX.Element {
  return (
    <RadixTooltip.Provider delayDuration={TOOLTIP_DELAY_MS}>
      <RadixTooltip.Root defaultOpen={defaultOpen}>
        <RadixTooltip.Trigger asChild {...trigger}>
          {children}
        </RadixTooltip.Trigger>
        <RadixTooltip.Portal container={getPortalContainer()}>
          <RadixTooltip.Content
            data-slot="tooltip"
            side={side}
            align={align}
            sideOffset={4}
            collisionPadding={8}
            className={TOOLTIP_SURFACE}
          >
            {content}
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
