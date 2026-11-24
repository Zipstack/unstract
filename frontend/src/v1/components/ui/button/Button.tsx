import { cn } from "@v1/lib/cn";
import { STATUS_ICONS } from "@v1/lib/icons";
import { cva, type VariantProps } from "class-variance-authority";
import type { LucideIcon } from "lucide-react";
import type { ComponentProps, JSX, KeyboardEvent, MouseEvent } from "react";

/** Variant and size classes; a router link that must look like a button takes them as `className`. */
export const buttonVariants = cva(
  [
    "ui:inline-flex ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-md ui:border ui:border-transparent ui:font-sans ui:font-medium ui:whitespace-nowrap ui:no-underline ui:outline-none ui:transition-colors ui:motion-reduce:transition-none",
    "ui:focus-visible:focus-ring ui:disabled:cursor-not-allowed ui:disabled:opacity-50 ui:aria-busy:cursor-progress ui:[&>svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        primary:
          "ui:bg-primary ui:text-primary-foreground ui:not-disabled:hover:bg-primary/90 ui:not-disabled:active:bg-primary/80",
        secondary:
          "ui:bg-secondary ui:text-secondary-foreground ui:not-disabled:hover:bg-secondary/80 ui:not-disabled:active:bg-secondary/70",
        outline:
          "ui:border-border ui:bg-card ui:text-foreground ui:not-disabled:hover:bg-accent ui:not-disabled:active:bg-border",
        ghost:
          "ui:bg-transparent ui:text-foreground ui:not-disabled:hover:bg-accent ui:not-disabled:active:bg-border",
        destructive:
          "ui:bg-destructive ui:text-destructive-foreground ui:not-disabled:hover:bg-destructive/90 ui:not-disabled:active:bg-destructive/80",
        link: "ui:bg-transparent ui:text-primary ui:underline-offset-2 ui:not-disabled:hover:underline ui:not-disabled:active:text-primary/80",
      },
      size: {
        lg: "ui:h-9 ui:gap-2 ui:px-3.5 ui:text-body ui:[&>svg]:size-4",
        md: "ui:h-8 ui:gap-2 ui:px-3 ui:text-body-small ui:[&>svg]:size-4",
        sm: "ui:h-7 ui:gap-1.5 ui:px-2.5 ui:text-body-small ui:[&>svg]:size-4",
        xs: "ui:h-6 ui:gap-1 ui:px-2 ui:text-caption ui:[&>svg]:size-3.5",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> &
  Readonly<{
    /** Glyph before the label; the spinner takes its place while loading. */
    leadingIcon?: LucideIcon;
    /** Glyph after the label. */
    trailingIcon?: LucideIcon;
    /** Shows a spinner and ignores activation; the button keeps focus. */
    loading?: boolean;
    "data-slot"?: string;
  }>;

// A direct child svg, so the size's icon rule sizes it like the icon it replaces.
const LoadingIcon = STATUS_ICONS.loading;

const ignore = (): void => undefined;

// Keys that activate a button or open a Radix menu trigger.
const ACTIVATION_KEYS = new Set(["Enter", " ", "ArrowDown"]);

// While loading it keeps focus but drops pointer-down, click and activation keys; other keys pass through.
function busyProps(onKeyDown: ButtonProps["onKeyDown"]) {
  return {
    "aria-busy": true,
    "aria-disabled": true,
    onPointerDown: ignore,
    onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => {
      if (ACTIVATION_KEYS.has(event.key)) {
        // Also stops a Space held across the end of loading from clicking.
        event.preventDefault();
      } else {
        onKeyDown?.(event);
      }
    },
    onClick: (event: MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
    },
  } as const;
}

function LeadingIcon({
  icon: Icon,
  loading,
}: Readonly<{ icon?: LucideIcon; loading: boolean }>) {
  if (loading) {
    return <LoadingIcon aria-hidden className="ui:motion-safe:animate-spin" />;
  }
  return Icon ? <Icon aria-hidden /> : null;
}

/** The one button: four heights, six variants, optional icons and a loading state. */
export function Button({
  variant,
  size,
  leadingIcon,
  trailingIcon: TrailingIcon,
  loading = false,
  type = "button",
  className,
  children,
  "data-slot": slot = "button",
  ...props
}: ButtonProps): JSX.Element {
  return (
    <button
      {...props}
      {...(loading ? busyProps(props.onKeyDown) : {})}
      type={type}
      data-slot={slot}
      className={cn(buttonVariants({ variant, size }), className)}
    >
      <LeadingIcon icon={leadingIcon} loading={loading} />
      {children}
      {TrailingIcon && <TrailingIcon aria-hidden />}
    </button>
  );
}
