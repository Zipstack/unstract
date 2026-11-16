import { cn } from "@v1/lib/cn";
import { LoaderCircle } from "lucide-react";
import type { JSX } from "react";

export type SpinnerProps = Readonly<{
  /**
   * `button` sits beside a button label; `inline` sits in running text. There
   * is deliberately no large size: a page or card loads with a skeleton.
   */
  size?: "button" | "inline";
  /** Read by screen readers; leave it out when the button text already says so. */
  label?: string;
  className?: string;
}>;

/** A spinner for inside buttons and inline text only (dev spec section 8). */
export function Spinner({
  size = "inline",
  label,
  className,
}: SpinnerProps): JSX.Element {
  const icon = (
    <LoaderCircle
      aria-hidden
      className={cn(
        "ui:shrink-0 ui:motion-safe:animate-spin",
        size === "button" ? "ui:size-4" : "ui:size-3.5",
        className,
      )}
    />
  );
  if (!label) {
    return (
      <span data-slot="spinner" className="ui:inline-flex">
        {icon}
      </span>
    );
  }
  return (
    <output data-slot="spinner" className="ui:inline-flex">
      {icon}
      <span className="ui:sr-only">{label}</span>
    </output>
  );
}
