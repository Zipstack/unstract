import { cn } from "@v1/lib/cn";
import { Tabs as RadixTabs } from "radix-ui";
import {
  type ComponentProps,
  createContext,
  type JSX,
  useContext,
} from "react";

/**
 * `bar`: the underline tabs of the Nav 3 tab bar (dev spec 683:135, frame
 * 584:47), 44 high with a 24px gap. `segmented`: the compact in-page switch
 * (frame 758:20028, "Connector type").
 */
export type TabsVariant = "bar" | "segmented";

const VariantContext = createContext<TabsVariant>("bar");

export type TabsProps = ComponentProps<typeof RadixTabs.Root> &
  Readonly<{ variant?: TabsVariant }>;

/**
 * Tabs with automatic activation by default (pass `activationMode="manual"`
 * to opt out): the arrow keys move between tabs and select
 * the one they land on; Home and End jump to the ends. The selected tab
 * carries `aria-selected="true"` and `data-state="active"`.
 */
export function Tabs({
  variant = "bar",
  className,
  ...props
}: TabsProps): JSX.Element {
  return (
    <VariantContext.Provider value={variant}>
      <RadixTabs.Root
        data-slot="tabs"
        data-variant={variant}
        activationMode="automatic"
        className={cn("ui:flex ui:flex-col", className)}
        {...props}
      />
    </VariantContext.Provider>
  );
}

export type TabsListProps = ComponentProps<typeof RadixTabs.List>;

/** The row of tabs. Give it an `aria-label` naming what the tabs switch. */
export function TabsList({ className, ...props }: TabsListProps): JSX.Element {
  const variant = useContext(VariantContext);
  return (
    <RadixTabs.List
      data-slot="tabs-list"
      className={cn(
        variant === "bar"
          ? "ui:flex ui:h-11 ui:items-stretch ui:gap-6"
          : "ui:inline-flex ui:w-fit ui:items-center ui:gap-1 ui:rounded-lg ui:bg-muted ui:p-1",
        className,
      )}
      {...props}
    />
  );
}

export type TabsTriggerProps = ComponentProps<typeof RadixTabs.Trigger>;

export function TabsTrigger({
  className,
  ...props
}: TabsTriggerProps): JSX.Element {
  const variant = useContext(VariantContext);
  return (
    <RadixTabs.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "ui:inline-flex ui:cursor-pointer ui:items-center ui:justify-center ui:gap-1.5 ui:whitespace-nowrap ui:border-0 ui:bg-transparent ui:font-sans ui:font-medium ui:text-muted-foreground ui:outline-none ui:focus-visible:focus-ring ui:disabled:cursor-not-allowed ui:disabled:opacity-50 ui:data-[state=active]:font-semibold ui:data-[state=active]:text-foreground",
        variant === "bar"
          ? "ui:relative ui:rounded-sm ui:px-0 ui:text-body ui:not-disabled:hover:text-foreground ui:after:absolute ui:after:inset-x-0 ui:after:bottom-0 ui:after:h-0.5 ui:after:rounded-full ui:data-[state=active]:after:bg-primary"
          : "ui:h-7 ui:rounded-md ui:px-4 ui:text-body-small ui:not-disabled:hover:text-foreground ui:data-[state=active]:bg-card ui:data-[state=active]:shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

export type TabsContentProps = ComponentProps<typeof RadixTabs.Content>;

export function TabsContent({
  className,
  ...props
}: TabsContentProps): JSX.Element {
  return (
    <RadixTabs.Content
      data-slot="tabs-content"
      className={cn("ui:outline-none ui:focus-visible:focus-ring", className)}
      {...props}
    />
  );
}
