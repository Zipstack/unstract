import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Loading spinner. Hand-written: shadcn has no registry entry for this, but the
 * Midnight Bloom mockups include one and antd's `Spin` (24 call-sites) needs a
 * replacement in P1-06.
 */
const spinnerVariants = cva("animate-spin text-muted-foreground", {
  variants: {
    size: {
      sm: "size-4",
      default: "size-6",
      lg: "size-8",
    },
  },
  defaultVariants: {
    size: "default",
  },
});

function Spinner({
  className,
  size,
  label = "Loading",
  ...props
}: Omit<React.ComponentPropsWithoutRef<typeof Loader2>, "ref"> &
  VariantProps<typeof spinnerVariants> & {
    /** Accessible name announced for the busy state. */
    label?: string;
  }) {
  return (
    <Loader2
      role="status"
      aria-label={label}
      className={cn(spinnerVariants({ size }), className)}
      {...props}
    />
  );
}

export { Spinner, spinnerVariants };
