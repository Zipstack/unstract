import { cn } from "@v1/lib/cn";
import { ChevronRight } from "lucide-react";
import { Slot } from "radix-ui";
import type { ComponentProps, JSX } from "react";

export type BreadcrumbProps = ComponentProps<"nav">;

/** A breadcrumb trail. The landmark is named "Breadcrumb" unless overridden. */
export function Breadcrumb({
  "aria-label": label = "Breadcrumb",
  ...props
}: BreadcrumbProps): JSX.Element {
  return <nav data-slot="breadcrumb" aria-label={label} {...props} />;
}

export function BreadcrumbList({
  className,
  ...props
}: ComponentProps<"ol">): JSX.Element {
  return (
    <ol
      data-slot="breadcrumb-list"
      className={cn(
        "ui:m-0 ui:flex ui:list-none ui:flex-wrap ui:items-center ui:gap-1.5 ui:p-0 ui:text-body-small ui:text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function BreadcrumbItem({
  className,
  ...props
}: ComponentProps<"li">): JSX.Element {
  return (
    <li
      data-slot="breadcrumb-item"
      className={cn("ui:inline-flex ui:items-center ui:gap-1.5", className)}
      {...props}
    />
  );
}

export type BreadcrumbLinkProps = ComponentProps<"a"> &
  Readonly<{
    /** Render the child (a router `Link`) with the link's classes instead of an `<a>`. */
    asChild?: boolean;
  }>;

export function BreadcrumbLink({
  asChild = false,
  className,
  ...props
}: BreadcrumbLinkProps): JSX.Element {
  const Component = asChild ? Slot.Root : "a";
  return (
    <Component
      data-slot="breadcrumb-link"
      className={cn(
        "ui:rounded-sm ui:text-muted-foreground ui:no-underline ui:outline-none ui:hover:text-foreground ui:focus-visible:focus-ring",
        className,
      )}
      {...props}
    />
  );
}

/** The current page: plain text, marked `aria-current="page"`. */
export function BreadcrumbPage({
  className,
  ...props
}: ComponentProps<"span">): JSX.Element {
  return (
    <span
      data-slot="breadcrumb-page"
      aria-current="page"
      className={cn("ui:font-medium ui:text-foreground", className)}
      {...props}
    />
  );
}

/** Sits in its own `<li>` between items; hidden from screen readers. */
export function BreadcrumbSeparator({
  className,
  children,
  ...props
}: ComponentProps<"li">): JSX.Element {
  return (
    <li
      data-slot="breadcrumb-separator"
      role="presentation"
      aria-hidden
      className={cn("ui:inline-flex ui:items-center", className)}
      {...props}
    >
      {children ?? <ChevronRight className="ui:size-3.5" />}
    </li>
  );
}
