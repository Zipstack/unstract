import * as React from "react";

import { cn } from "@/lib/utils";

/*
 * No `shadow-sm` — that was the "left and right borders are missing" bug.
 *
 * Tailwind's `shadow-sm` is `0 1px 3px` + `0 1px 2px`: a purely VERTICAL
 * offset. It lays a dark smudge immediately below the top and bottom edges
 * and contributes nothing to the sides, so the horizontals read as a firm
 * line while the verticals are left as a bare 1px hairline at ~1.2 contrast.
 * The asymmetry is what the eye picks up — the side borders are drawn, they
 * just look absent next to shadow-reinforced top and bottom edges.
 *
 * The antd reference computes `box-shadow: none` on its inputs, so dropping
 * it matches the reference and makes all four sides read equally. Removed
 * from Textarea and the Select trigger too, or those controls would keep the
 * asymmetry while sitting next to a fixed Input in the same form.
 */
const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        "flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-base transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        className,
      )}
      ref={ref}
      {...props}
    />
  );
});
Input.displayName = "Input";

export { Input };
