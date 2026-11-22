import { useCallback, useLayoutEffect, useRef } from "react";

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

/** One ask at a time; a yes closes only if the dialog stayed open and is not busy. */
function useAsk(open: boolean, busy: boolean) {
  const busyNow = useRef(busy);
  const pending = useRef<object | null>(null);
  useLayoutEffect(() => {
    busyNow.current = busy;
    if (!open) {
      pending.current = null;
    }
  }, [busy, open]);
  const ask = useCallback((guard: Guard, close: () => void) => {
    const token = {};
    pending.current = token;
    void allowed(guard).then((ok) => {
      if (pending.current !== token) {
        return;
      }
      pending.current = null;
      if (ok && !busyNow.current) {
        close();
      }
    });
  }, []);
  return { pending, ask };
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
  const { pending, ask } = useAsk(open, busy);
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
        ask(beforeClose, () => onOpenChange(false));
      } else {
        onOpenChange(false);
      }
    },
    [ask, beforeClose, busy, onOpenChange, pending],
  );
}
