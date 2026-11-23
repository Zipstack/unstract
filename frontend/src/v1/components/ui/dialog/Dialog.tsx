import { Button, type ButtonProps } from "@v1/components/ui/button";
import {
  type DismissHandlers,
  dismissGuards,
  OVERLAY_SCRIM,
  OverlayFooter,
  OverlayHeader,
  type OverlayHeaderProps,
  useReturnFocus,
} from "@v1/components/ui/overlay";
import { cn } from "@v1/lib/cn";
import { getPortalContainer } from "@v1/lib/portal";
import { Dialog as RadixDialog } from "radix-ui";
import {
  type ComponentProps,
  type ComponentPropsWithoutRef,
  createContext,
  type JSX,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { type CloseGuard, useGuardedClose } from "./useGuardedClose";

type DialogState = Readonly<{
  open: boolean;
  busy: boolean;
  dismissible: boolean;
}>;

const DialogContext = createContext<DialogState>({
  open: false,
  busy: false,
  dismissible: true,
});

export type DialogProps = Omit<CloseGuard, "onOpenChange"> &
  Readonly<{
    open?: boolean;
    defaultOpen?: boolean;
    onOpenChange?: (open: boolean) => void;
    /** Default true; false keeps the dialog open on an outside click. */
    dismissible?: boolean;
    children: ReactNode;
  }>;

/** Controlled when `open` is given; otherwise the dialog keeps its own state. */
function useOpenState(
  open: boolean | undefined,
  defaultOpen: boolean,
  onOpenChange?: (open: boolean) => void,
) {
  const [ownOpen, setOwnOpen] = useState(defaultOpen);
  const change = useCallback(
    (next: boolean) => {
      setOwnOpen(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
  return [open ?? ownOpen, change] as const;
}

/** The one dialog: every close path passes `busy` and `beforeClose` first. */
export function Dialog({
  open,
  defaultOpen = false,
  onOpenChange,
  busy = false,
  dismissible = true,
  beforeClose,
  children,
}: DialogProps): JSX.Element {
  const [isOpen, change] = useOpenState(open, defaultOpen, onOpenChange);
  const request = useGuardedClose({
    open: isOpen,
    busy,
    beforeClose,
    onOpenChange: change,
  });
  const state = useMemo(
    () => ({ open: isOpen, busy, dismissible }),
    [isOpen, busy, dismissible],
  );
  return (
    <DialogContext.Provider value={state}>
      <RadixDialog.Root open={isOpen} onOpenChange={request}>
        {children}
      </RadixDialog.Root>
    </DialogContext.Provider>
  );
}

export const DialogTrigger = RadixDialog.Trigger;

const SIZE_CLASS = {
  sm: "ui:max-w-lg",
  md: "ui:max-w-xl",
  lg: "ui:max-w-4xl",
  full: "ui:h-full ui:max-w-7xl",
} as const;

export type DialogSize = keyof typeof SIZE_CLASS;

// Keeps the panel 16px inside the viewport; clicks on it fall through to the scrim.
const FRAME =
  "ui:pointer-events-none ui:fixed ui:inset-0 ui:z-50 ui:flex ui:items-center ui:justify-center ui:p-4";

const PANEL =
  "ui:pointer-events-auto ui:flex ui:max-h-full ui:w-full ui:flex-col ui:overflow-hidden ui:rounded-xl ui:border ui:border-border ui:bg-popover ui:text-popover-foreground ui:shadow-xl ui:outline-none";

const BODY_FIELD = [
  "input:not([type=hidden])",
  "select",
  "textarea",
  "button",
  "a[href]",
  "[tabindex]",
]
  .map(
    (tag) =>
      `[data-slot=dialog-body] ${tag}:not(:disabled):not([tabindex="-1"])`,
  )
  .join(", ");

// A hidden or disabled control does not take focus; a group hands it to its active item.
function takesFocus(element: HTMLElement): boolean {
  element.focus();
  return element.contains(element.ownerDocument.activeElement);
}

/** First focus: the control marked `data-autofocus`, else the body's first control, else Radix's default. */
function focusDefault(event: Event): void {
  const root = event.target;
  if (!(root instanceof HTMLElement)) {
    return;
  }
  const candidates = [
    ...root.querySelectorAll<HTMLElement>("[data-autofocus]"),
    ...root.querySelectorAll<HTMLElement>(BODY_FIELD),
  ];
  if (candidates.some(takesFocus)) {
    event.preventDefault();
  }
}

type ContentProps = ComponentPropsWithoutRef<typeof RadixDialog.Content>;

export type DialogContentProps = Omit<
  ContentProps,
  "asChild" | "forceMount" | "onOpenAutoFocus" | "onCloseAutoFocus"
> &
  Readonly<{ size?: DialogSize; "data-slot"?: string }>;

// The shared rules, plus no outside-click close when the dialog is not dismissible.
function guardsFor(
  { busy, dismissible }: DialogState,
  own: DismissHandlers,
): DismissHandlers {
  const outside = own.onInteractOutside;
  return dismissGuards(busy, {
    ...own,
    onInteractOutside: dismissible
      ? outside
      : (event) => {
          outside?.(event);
          event.preventDefault();
        },
  });
}

/** The panel: portal, scrim, size, dismiss rules and focus handling. */
export function DialogContent({
  size = "md",
  className,
  onEscapeKeyDown,
  onInteractOutside,
  "data-slot": slot = "dialog",
  ...props
}: DialogContentProps): JSX.Element {
  const state = useContext(DialogContext);
  const returnFocus = useReturnFocus(state.open);
  return (
    <RadixDialog.Portal container={getPortalContainer()}>
      <RadixDialog.Overlay data-slot="dialog-scrim" className={OVERLAY_SCRIM} />
      <div className={FRAME}>
        <RadixDialog.Content
          {...props}
          {...guardsFor(state, { onEscapeKeyDown, onInteractOutside })}
          data-slot={slot}
          aria-busy={state.busy || undefined}
          onOpenAutoFocus={focusDefault}
          onCloseAutoFocus={returnFocus}
          className={cn(PANEL, SIZE_CLASS[size], className)}
        />
      </div>
    </RadixDialog.Portal>
  );
}

export type DialogHeaderProps = Omit<OverlayHeaderProps, "busy">;

/** Title, optional description and the close button, disabled while busy. */
export function DialogHeader(props: DialogHeaderProps): JSX.Element {
  const { busy } = useContext(DialogContext);
  return <OverlayHeader {...props} busy={busy} />;
}

/** The scrolling middle; its first control takes focus when the dialog opens. */
export function DialogBody({
  className,
  ...props
}: ComponentProps<"div">): JSX.Element {
  return (
    <div
      data-slot="dialog-body"
      {...props}
      className={cn(
        "ui:flex ui:min-h-0 ui:flex-1 ui:flex-col ui:gap-4 ui:overflow-y-auto ui:px-6 ui:py-5 ui:text-body ui:text-foreground",
        className,
      )}
    />
  );
}

export const DialogFooter = OverlayFooter;

export type DialogCancelProps = Omit<ButtonProps, "variant" | "disabled">;

/** Closes the dialog through the same guards; disabled while busy. */
export function DialogCancel({
  children = "Cancel",
  size = "lg",
  ...props
}: DialogCancelProps): JSX.Element {
  const { busy } = useContext(DialogContext);
  return (
    <RadixDialog.Close asChild>
      <Button {...props} variant="outline" size={size} disabled={busy}>
        {children}
      </Button>
    </RadixDialog.Close>
  );
}
