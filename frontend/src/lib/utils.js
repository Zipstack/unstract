import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge conditional class names, with later Tailwind utilities winning over
 * earlier conflicting ones. Standard shadcn/ui helper.
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
