import { cn } from "@v1/lib/cn";
import { cva, type VariantProps } from "class-variance-authority";
import type { LucideIcon } from "lucide-react";
import type { ComponentProps, JSX } from "react";

const iconButtonVariants = cva(
  "ui:inline-flex ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:border ui:border-transparent ui:p-0 ui:outline-none ui:transition-colors ui:motion-reduce:transition-none ui:focus-visible:focus-ring ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:[&>svg]:size-4",
  {
    variants: {
      variant: {
        ghost:
          "ui:bg-transparent ui:text-muted-foreground ui:hover:bg-accent ui:hover:text-foreground ui:active:bg-border",
        outline:
          "ui:border-border ui:bg-card ui:text-foreground ui:hover:bg-accent ui:active:bg-border",
      },
      size: {
        md: "ui:size-8 ui:rounded-md",
        sm: "ui:size-7 ui:rounded-sm",
      },
    },
    defaultVariants: { variant: "ghost", size: "md" },
  },
);

const SELECTED =
  "ui:border-transparent ui:bg-primary ui:text-primary-foreground ui:hover:bg-primary/90 ui:hover:text-primary-foreground ui:active:bg-primary/80";

/** The button shows no text, so the types require a name. */
type IconButtonName =
  | Readonly<{ "aria-label": string }>
  | Readonly<{ "aria-labelledby": string }>;

export type IconButtonProps = Omit<
  ComponentProps<"button">,
  "children" | "aria-pressed"
> &
  VariantProps<typeof iconButtonVariants> &
  Readonly<{
    icon: LucideIcon;
    /** A toggle's on state: sets `aria-pressed` and the primary fill. */
    selected?: boolean;
    "data-slot"?: string;
  }> &
  IconButtonName;

/** A square icon-only button: 32, or 28 in dense rows. */
export function IconButton({
  icon: Icon,
  variant,
  size,
  selected,
  type = "button",
  className,
  "data-slot": slot = "icon-button",
  ...props
}: IconButtonProps): JSX.Element {
  return (
    <button
      {...props}
      type={type}
      data-slot={slot}
      aria-pressed={selected}
      className={cn(
        iconButtonVariants({ variant, size }),
        selected && SELECTED,
        className,
      )}
    >
      <Icon aria-hidden />
    </button>
  );
}
