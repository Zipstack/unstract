import { Popover as PopoverPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

const Popover = PopoverPrimitive.Root;

const PopoverTrigger = PopoverPrimitive.Trigger;

const PopoverAnchor = PopoverPrimitive.Anchor;

const PopoverContent = React.forwardRef<
  React.ComponentRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "center", sideOffset = 4, onWheel, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      // A popover open inside a Modal is portalled to `document.body`, so it
      // sits outside both Radix's scroll lock and the dialog content it
      // shards — and react-remove-scroll cancels every `wheel` it sees on
      // `document` from anywhere else. That left popover lists scrollable by
      // dragging the scrollbar but dead to the mouse wheel. Its listener is
      // on `document` and not capturing, so stopping propagation here keeps
      // it from ever running; the browser still scrolls natively.
      onWheel={(event) => {
        onWheel?.(event);
        event.stopPropagation();
      }}
      className={cn(
        // `max-h` + scroll: Radix measures the space actually available on
        // the chosen side and exposes it as this variable. Without it a tall
        // popover (the 456px emoji picker, anchored low in a modal) simply
        // overflows the viewport and its bottom rows are unreachable.
        "z-50 max-h-[var(--radix-popover-content-available-height)] w-72 overflow-y-auto rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 origin-[var(--radix-popover-content-transform-origin)]",
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;

export { Popover, PopoverAnchor, PopoverContent, PopoverTrigger };
