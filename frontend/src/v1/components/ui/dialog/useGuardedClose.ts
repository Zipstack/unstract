import {
  type RefObject,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

export type CloseGuard = Readonly<{
  /** While true, a request to close is ignored. */
  busy?: boolean;
  /** The dirty guard: asked before every close; false or a throw keeps the dialog open. */
  beforeClose?: () => boolean | Promise<boolean>;
  onOpenChange: (open: boolean) => void;
}>;

type Guard = NonNullable<CloseGuard["beforeClose"]>;

// A guard that throws or rejects keeps the dialog open; the error is logged.
async function allowed(guard: Guard): Promise<boolean> {
  try {
    return await guard();
  } catch (error) {
    console.error(
      "[v1 dialog] beforeClose failed; the dialog stays open",
      error,
    );
    return false;
  }
}

/** The pending ask's token; a close drops it, so its answer is ignored. */
function usePendingAsk(open: boolean): RefObject<object | null> {
  const pending = useRef<object | null>(null);
  useLayoutEffect(() => {
    if (!open) {
      pending.current = null;
    }
  }, [open]);
  return pending;
}

/** A yes closes when it commits (never after unmount), unless the dialog is busy or closed by then. */
function useCloseOnYes(
  pending: RefObject<object | null>,
  busy: boolean,
  onOpenChange: (open: boolean) => void,
): (token: object) => void {
  const [yes, setYes] = useState<object | null>(null);
  // It commits with the guard's own updates, so a busy the guard set and cleared reads false.
  useLayoutEffect(() => {
    if (yes === null) {
      return;
    }
    setYes(null);
    if (yes === pending.current) {
      pending.current = null;
      if (!busy) {
        onOpenChange(false);
      }
    }
  }, [yes, busy, onOpenChange, pending]);
  return setYes;
}

/** Asks the guard under a new token; a no or a throw ends the ask at once. */
function ask(
  pending: RefObject<object | null>,
  guard: Guard,
  onYes: (token: object) => void,
): void {
  const token = {};
  pending.current = token;
  void allowed(guard).then((ok) => {
    if (pending.current !== token) {
      return;
    }
    if (ok) {
      onYes(token);
    } else {
      pending.current = null;
    }
  });
}

/**
 * Wraps `onOpenChange` so every close path first passes `busy` and
 * `beforeClose`; a request while the guard is asking is ignored.
 */
export function useGuardedClose({
  open,
  busy = false,
  beforeClose,
  onOpenChange,
}: CloseGuard & Readonly<{ open: boolean }>): (open: boolean) => void {
  const pending = usePendingAsk(open);
  const closeOnYes = useCloseOnYes(pending, busy, onOpenChange);
  return useCallback(
    (next: boolean) => {
      if (next) {
        onOpenChange(true);
        return;
      }
      if (busy || pending.current) {
        return;
      }
      if (beforeClose) {
        ask(pending, beforeClose, closeOnYes);
      } else {
        onOpenChange(false);
      }
    },
    [beforeClose, busy, closeOnYes, onOpenChange, pending],
  );
}
