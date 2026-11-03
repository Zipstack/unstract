import { cn } from "@v1/lib/cn";
import { type NotifyInput, type NotifyKind, setNotifier } from "@v1/lib/notify";
import { getPortalContainer } from "@v1/lib/portal";
import { X } from "lucide-react";
import { Toast as RadixToast } from "radix-ui";
import { type JSX, useCallback, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";
import { KIND_ICON, KIND_TEXT } from "./kinds";

/** How long a toast stays when it is not persistent. */
export const TOAST_DURATION_MS = 6000;

/** Toasts shown at once; older ones close first. */
export const MAX_TOASTS = 3;

type Entry = NotifyInput & Readonly<{ id: string }>;

export type ToasterProps = Readonly<{
  /** Overrides the default timeout (tests, or a page that needs longer). */
  duration?: number;
  /** Where the viewport renders; the v1 portal container by default. */
  container?: HTMLElement;
}>;

let sequence = 0;
const nextId = () => {
  sequence += 1;
  return `toast-${sequence}`;
};

/**
 * The single toast region of v1. Mount it once, inside the v1 root; it
 * registers itself as the notifier, so `notify()` and `toast.*` reach it.
 * Toasts stack bottom-right, pause while hovered or focused, and F8 moves
 * focus to them so an action is reachable by keyboard.
 */
export function Toaster({
  duration = TOAST_DURATION_MS,
  container,
}: ToasterProps): JSX.Element {
  const [entries, setEntries] = useState<readonly Entry[]>([]);
  const [target, setTarget] = useState<HTMLElement | null>(container ?? null);

  const remove = useCallback((id: string) => {
    setEntries((all) => all.filter((e) => e.id !== id));
  }, []);

  useLayoutEffect(() => {
    if (!container) {
      setTarget(getPortalContainer());
    }
    return setNotifier({
      show: (input) => {
        const id = input.id ?? nextId();
        setEntries((all) =>
          [...all.filter((e) => e.id !== id), { ...input, id }].slice(
            -MAX_TOASTS,
          ),
        );
        return id;
      },
      dismiss: remove,
    });
  }, [remove, container]);

  const viewport = (
    <RadixToast.Viewport
      label="Notifications ({hotkey})"
      className="ui:fixed ui:right-0 ui:bottom-0 ui:box-border ui:z-50 ui:m-0 ui:flex ui:max-h-screen ui:w-full ui:max-w-108 ui:list-none ui:flex-col ui:gap-3 ui:p-4 ui:outline-none"
    />
  );

  return (
    <RadixToast.Provider
      duration={duration}
      swipeDirection="right"
      label="Notification"
    >
      {entries.map((entry) => (
        <ToastItem
          key={entry.id}
          entry={entry}
          onClose={() => remove(entry.id)}
        />
      ))}
      {target ? createPortal(viewport, target) : null}
    </RadixToast.Provider>
  );
}

type ToastItemProps = Readonly<{ entry: Entry; onClose: () => void }>;

function ToastItem({ entry, onClose }: ToastItemProps): JSX.Element {
  const Icon = KIND_ICON[entry.kind];

  return (
    <RadixToast.Root
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      duration={entry.persistent ? Number.POSITIVE_INFINITY : undefined}
      type={assertive(entry.kind) ? "foreground" : "background"}
      data-slot="toast"
      data-kind={entry.kind}
      className={cn(
        "ui:box-border ui:flex ui:w-full ui:items-start ui:gap-3 ui:rounded-lg ui:border ui:border-border ui:bg-popover ui:py-3.5 ui:pr-3.5 ui:pl-4 ui:text-popover-foreground ui:shadow-md ui:focus-visible:focus-ring",
      )}
    >
      <Icon
        aria-hidden
        className={cn(
          "ui:mt-px ui:size-4.5 ui:shrink-0",
          KIND_TEXT[entry.kind],
        )}
      />
      <div className="ui:flex ui:min-w-0 ui:flex-1 ui:flex-col ui:gap-1">
        <RadixToast.Title className="ui:text-body ui:font-semibold ui:text-foreground">
          {entry.title}
        </RadixToast.Title>
        {entry.description ? (
          <RadixToast.Description className="ui:text-body-small ui:text-muted-foreground">
            {entry.description}
          </RadixToast.Description>
        ) : null}
        {entry.action ? (
          <RadixToast.Action
            altText={entry.action.label}
            onClick={entry.action.onSelect}
            className="ui:mt-1 ui:cursor-pointer ui:self-start ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:text-body-small ui:font-medium ui:text-primary ui:hover:underline ui:focus-visible:focus-ring"
          >
            {entry.action.label}
          </RadixToast.Action>
        ) : null}
      </div>
      <RadixToast.Close
        aria-label="Dismiss notification"
        className="ui:inline-flex ui:size-6 ui:shrink-0 ui:cursor-pointer ui:items-center ui:justify-center ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:text-muted-foreground ui:hover:bg-accent ui:hover:text-foreground ui:focus-visible:focus-ring"
      >
        <X aria-hidden className="ui:size-3.5" />
      </RadixToast.Close>
    </RadixToast.Root>
  );
}

/** Errors interrupt; everything else waits for a pause. */
function assertive(kind: NotifyKind): boolean {
  return kind === "error";
}
