import { cn } from "@/lib/utils";

/**
 * Keyboard key hint (e.g. ⌘ K in the search bar). Hand-written: shadcn has no
 * registry entry, but the Midnight Bloom mockups use it in the command/search
 * affordance.
 */
function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "pointer-events-none inline-flex h-5 select-none items-center gap-1",
        "rounded border border-border bg-muted px-1.5",
        "font-mono text-[10px] font-medium text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export { Kbd };
