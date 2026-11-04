import { cn } from "@v1/lib/cn";
import type { NotifyKind } from "@v1/lib/notify";
import type { ComponentProps, JSX, ReactNode } from "react";
import { KIND_BORDER, KIND_ICON, KIND_TEXT } from "./kinds";

export type InlineAlertProps = Omit<ComponentProps<"div">, "title" | "role"> &
  Readonly<{
    kind?: NotifyKind;
    title: ReactNode;
    children?: ReactNode;
    /** Shows a Retry button; the error state's one action. */
    onRetry?: () => void;
    retryLabel?: string;
  }>;

/**
 * A message above the content it concerns: dev spec section 8, "inline, above
 * the content it concerns, with a retry". Errors are announced at once
 * (`role="alert"`); other kinds wait for a pause (`role="status"`).
 */
export function InlineAlert({
  kind = "error",
  title,
  children,
  onRetry,
  retryLabel = "Retry",
  className,
  ...props
}: InlineAlertProps): JSX.Element {
  const Icon = KIND_ICON[kind];
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      data-slot="inline-alert"
      data-kind={kind}
      className={cn(
        // `destructive-muted` has no value yet, so the fill is `muted` as in frame 622:1320.
        "ui:box-border ui:flex ui:items-start ui:gap-2.5 ui:rounded-lg ui:border ui:bg-muted ui:px-3.5 ui:py-3 ui:text-foreground",
        KIND_BORDER[kind],
        className,
      )}
      {...props}
    >
      <Icon
        aria-hidden
        className={cn("ui:mt-0.5 ui:size-4 ui:shrink-0", KIND_TEXT[kind])}
      />
      <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-1">
        <p className="ui:m-0 ui:text-body-small ui:font-semibold">{title}</p>
        {children ? (
          <div className="ui:text-caption ui:text-muted-foreground">
            {children}
          </div>
        ) : null}
      </div>
      {onRetry ? (
        <button
          type="button"
          onClick={() => onRetry()}
          className="ui:inline-flex ui:h-7 ui:shrink-0 ui:cursor-pointer ui:items-center ui:rounded-sm ui:border ui:border-input ui:bg-background ui:px-2.5 ui:text-body-small ui:font-medium ui:text-foreground ui:hover:bg-accent ui:focus-visible:focus-ring"
        >
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
