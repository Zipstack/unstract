import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/** The type roles from the `type` token family, as `ui:text-<role>` utilities. */
export const TYPE_ROLES = [
  "display",
  "page-title",
  "section-title",
  "body",
  "body-small",
  "caption",
  "overline",
  "mono",
] as const;

// tailwind-merge knows only the stock text scale; without the roles it reads
// `ui:text-body` as a colour and drops it beside `ui:text-foreground`.
const twMerge = extendTailwindMerge({
  prefix: "ui",
  extend: { theme: { text: [...TYPE_ROLES] } },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
