import { Switch as SwitchPrimitives } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

const Switch = React.forwardRef<
  React.ComponentRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
      /*
       * Keyed off `aria-checked`, not `data-state`. A Radix parent that takes
       * this as an `asChild` trigger — `<Tooltip><Switch checked/></Tooltip>`,
       * which is how the API Deployments toggle is built — merges its OWN
       * `data-state` (the tooltip's open/closed state) onto this element,
       * flipping "checked" to "closed". `aria-checked` survives that merge, so
       * an enabled deployment no longer renders as an empty grey pill.
       */
      "aria-checked:bg-primary aria-[checked=false]:bg-input",
      className,
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitives.Thumb
      className={cn(
        "pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0",
      )}
    />
  </SwitchPrimitives.Root>
));
Switch.displayName = SwitchPrimitives.Root.displayName;

export { Switch };
