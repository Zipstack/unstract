import { cn } from "@v1/lib/cn";
import { ACTION_ICONS } from "@v1/lib/icons";
import { Slot } from "radix-ui";
import type { ComponentProps, JSX } from "react";

/** Inline link classes; the link keeps the size of the text around it. */
export const LINK_CLASS =
  "ui:rounded-sm ui:text-primary ui:underline ui:underline-offset-2 ui:outline-none ui:hover:text-primary/80 ui:focus-visible:focus-ring";

const ExternalIcon = ACTION_ICONS.openExternal;
const NEW_TAB = { target: "_blank", rel: "noopener noreferrer" } as const;

/** The external marker and its screen-reader text. */
function ExternalMarker() {
  return (
    <>
      <ExternalIcon
        aria-hidden
        className="ui:ms-0.5 ui:inline-block ui:size-3.5 ui:align-middle"
      />
      <span className="ui:sr-only"> (opens in a new tab)</span>
    </>
  );
}

type LinkMode =
  | Readonly<{
      /** Opens in a new tab and shows the external marker. */
      external?: boolean;
      asChild?: false;
    }>
  | Readonly<{
      /** Render the child (a router link) with the link's classes instead of an `<a>`. */
      asChild: true;
      external?: never;
    }>;

export type LinkProps = ComponentProps<"a"> & LinkMode;

/** An inline text link, optionally marked as opening a new tab. */
export function Link({
  asChild = false,
  external = false,
  className,
  children,
  ...props
}: LinkProps): JSX.Element {
  const classes = cn(LINK_CLASS, className);
  if (asChild) {
    return (
      <Slot.Root data-slot="link" className={classes} {...props}>
        {children}
      </Slot.Root>
    );
  }
  return (
    <a
      data-slot="link"
      className={classes}
      {...(external ? NEW_TAB : {})}
      {...props}
    >
      {children}
      {external && <ExternalMarker />}
    </a>
  );
}
