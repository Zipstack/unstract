import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

/*
 * `cursor-pointer` is explicit because Tailwind v4 dropped the preflight rule
 * that gave `<button>` a hand cursor in v3. antd set it on every button, so
 * losing it made the whole app feel inert on hover — the effect was app-wide,
 * not confined to one screen. `disabled:pointer-events-none` still wins for
 * disabled buttons, so they keep the default arrow.
 */
const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive:
          "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:bg-destructive/60 dark:focus-visible:ring-destructive/40",
        outline:
          "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        /*
         * Heights match the antd reference exactly: 32 / 24 / 40 for
         * default / sm / lg. shadcn ships 36 / 32 / 40, which put every
         * default control 4px taller than the app it is replacing and
         * collapsed the visual gap between default and small.
         */
        default: "h-8 px-4 py-2 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-md px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        /* Same 24px height as `xs`, which is intended: antd has no size below
         * `small`, so the two coincide on height and differ only in type size
         * and padding. The antd shim maps `size="small"` here. */
        sm: "h-6 gap-1.5 rounded-md px-3 has-[>svg]:px-2.5",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        icon: "size-9",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

/**
 * forwardRef matters here: this Button is rendered as the child of Radix
 * triggers (Dropdown, Popover, Tooltip) via `asChild`, which attaches its
 * handlers through a ref. Without it those triggers are silently inert —
 * the Prompt Studio Export menu never opened and fired no request at all.
 */
/*
 * Typed because the antd-* shims wrap this component: without a props type
 * here, TypeScript cannot verify that a shim passes a real `variant`/`size`,
 * and the whole point of typing the shim layer is to make those boundaries
 * checkable.
 */
export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Render the child element instead of a <button> (Radix `asChild`). */
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = "default",
    size = "default",
    asChild = false,
    ...props
  },
  ref,
) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      ref={ref}
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
});

export { Button, buttonVariants };
