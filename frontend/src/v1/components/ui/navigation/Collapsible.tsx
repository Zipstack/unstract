import { cn } from "@v1/lib/cn";
import { ChevronDown } from "lucide-react";
import { Collapsible as RadixCollapsible } from "radix-ui";
import type { ComponentProps, JSX } from "react";

export type CollapsibleProps = ComponentProps<typeof RadixCollapsible.Root>;

/** One region shown and hidden by its trigger (the run panels of frame 756:1190). */
export function Collapsible(props: CollapsibleProps): JSX.Element {
  return <RadixCollapsible.Root data-slot="collapsible" {...props} />;
}

export type CollapsibleTriggerProps = ComponentProps<
  typeof RadixCollapsible.Trigger
>;

/**
 * The chip trigger of the utility bar ("Debug panel ⌄"): label and optional
 * leading icon, with a chevron that turns when open. Pass `asChild` to use
 * your own control instead; it still gets `aria-expanded` and
 * `aria-controls`.
 */
export function CollapsibleTrigger({
  className,
  children,
  asChild = false,
  ...props
}: CollapsibleTriggerProps): JSX.Element {
  return (
    <RadixCollapsible.Trigger
      data-slot="collapsible-trigger"
      asChild={asChild}
      className={
        asChild
          ? className
          : cn(
              "ui:group ui:inline-flex ui:h-8 ui:cursor-pointer ui:items-center ui:gap-1.5 ui:rounded-md ui:border-0 ui:bg-transparent ui:px-2.5 ui:font-sans ui:text-body-small ui:font-medium ui:text-foreground ui:outline-none ui:not-disabled:hover:bg-accent ui:focus-visible:focus-ring ui:disabled:cursor-not-allowed ui:disabled:opacity-50 ui:data-[state=open]:bg-accent",
              className,
            )
      }
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {children}
          <ChevronDown
            aria-hidden
            className="ui:size-3 ui:shrink-0 ui:text-muted-foreground ui:transition-transform ui:motion-reduce:transition-none ui:group-data-[state=open]:rotate-180"
          />
        </>
      )}
    </RadixCollapsible.Trigger>
  );
}

export function CollapsibleContent(
  props: ComponentProps<typeof RadixCollapsible.Content>,
): JSX.Element {
  return (
    <RadixCollapsible.Content data-slot="collapsible-content" {...props} />
  );
}
