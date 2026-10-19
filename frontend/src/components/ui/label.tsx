import { Label as LabelPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

/*
 * forwardRef rather than a plain function, so the ref is part of the declared
 * type. `FormLabel` renders this with a `ref`; as a plain function component
 * that did not TYPE-check, because `ComponentPropsWithoutRef` (as the name
 * says) has no `ref`.
 *
 * At runtime it worked either way — React 19 treats `ref` as an ordinary prop
 * for function components, so the `{...props}` spread carried it through to
 * LabelPrimitive.Root. Verified directly rather than assumed: a plain function
 * component that only spreads props does receive a working ref under React 19.
 * So this is a typing correction, not a bug fix — worth making because the
 * declared surface should say what the component accepts.
 */
const Label = React.forwardRef<
  React.ComponentRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    data-slot="label"
    className={cn(
      "flex items-center gap-2 text-sm leading-none font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
