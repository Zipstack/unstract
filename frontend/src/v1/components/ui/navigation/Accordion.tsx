import { cn } from "@v1/lib/cn";
import { ChevronDown } from "lucide-react";
import { Accordion as RadixAccordion } from "radix-ui";
import type { ComponentProps, JSX } from "react";

export type AccordionProps = ComponentProps<typeof RadixAccordion.Root>;

/**
 * Sections that open and close in place. `type="single"` keeps one open
 * (add `collapsible` to allow none); `type="multiple"` lets several open.
 * Up and Down move between headers, Home and End jump to the ends.
 */
export function Accordion({
  className,
  ...props
}: AccordionProps): JSX.Element {
  return (
    <RadixAccordion.Root
      data-slot="accordion"
      className={cn(
        "ui:flex ui:flex-col ui:rounded-lg ui:border ui:border-border ui:bg-card",
        className,
      )}
      {...props}
    />
  );
}

export function AccordionItem({
  className,
  ...props
}: ComponentProps<typeof RadixAccordion.Item>): JSX.Element {
  return (
    <RadixAccordion.Item
      data-slot="accordion-item"
      className={cn(
        "ui:border-0 ui:border-b ui:border-solid ui:border-border ui:last:border-b-0",
        className,
      )}
      {...props}
    />
  );
}

export function AccordionTrigger({
  className,
  children,
  ...props
}: ComponentProps<typeof RadixAccordion.Trigger>): JSX.Element {
  return (
    <RadixAccordion.Header className="ui:m-0 ui:flex">
      <RadixAccordion.Trigger
        data-slot="accordion-trigger"
        className={cn(
          "ui:group ui:flex ui:flex-1 ui:cursor-pointer ui:items-center ui:justify-between ui:gap-3 ui:rounded-lg ui:border-0 ui:bg-transparent ui:px-4 ui:py-3 ui:text-left ui:font-sans ui:text-body ui:font-semibold ui:text-foreground ui:outline-none ui:focus-visible:focus-ring ui:disabled:cursor-not-allowed ui:disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
        <ChevronDown
          aria-hidden
          className="ui:size-4 ui:shrink-0 ui:text-muted-foreground ui:transition-transform ui:motion-reduce:transition-none ui:group-data-[state=open]:rotate-180"
        />
      </RadixAccordion.Trigger>
    </RadixAccordion.Header>
  );
}

export function AccordionContent({
  className,
  children,
  ...props
}: ComponentProps<typeof RadixAccordion.Content>): JSX.Element {
  return (
    <RadixAccordion.Content
      data-slot="accordion-content"
      className={cn(
        "ui:overflow-hidden ui:text-body-small ui:text-muted-foreground",
        className,
      )}
      {...props}
    >
      <div className="ui:px-4 ui:pb-4">{children}</div>
    </RadixAccordion.Content>
  );
}
