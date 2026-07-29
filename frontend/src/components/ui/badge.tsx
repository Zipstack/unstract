import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground shadow hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground shadow hover:bg-destructive/80",
        outline: "text-foreground",
        // P0-13: status variants for the "Done" / "In Process" / "Enabled"
        // badges used throughout the app. Backed by the --success / --warning
        // tokens added to the Midnight Bloom palette (§2.5.1).
        success:
          "border-transparent bg-success text-white shadow hover:bg-success/80",
        warning:
          "border-transparent bg-warning text-white shadow hover:bg-warning/80",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

/*
 * forwardRef so the ref is part of the declared surface — the antd `Tag` shim
 * renders Badge with one. As with `Label`, React 19 would carry the ref
 * through the props spread at runtime either way; declaring it keeps the type
 * honest about what the component accepts.
 */
const Badge = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>
>(({ className, variant, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(badgeVariants({ variant }), className)}
    {...props}
  />
));
Badge.displayName = "Badge";

export { Badge, badgeVariants };
